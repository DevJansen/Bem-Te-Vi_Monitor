"""Análise offline de vídeos importados (cartão de memória) com IA sensível.

Fluxo completo:

1. O vídeo é armazenado em ``app-data/imports/`` e um *job* é criado no
   registro em memória deste serviço.
2. Uma thread de trabalho lê o vídeo quadro a quadro (com passo configurável),
   roda o YOLOv8 com um limiar **mais sensível** que o da captura ao vivo e
   agrega as detecções em *aves distintas* por associação temporal (IoU +
   proximidade de centro).
3. Para cada ave distinta, re-lê o melhor quadro do vídeo, salva a miniatura e
   o recorte ampliado, cria automaticamente uma visita na Galeria e gera
   (best-effort) um clipe curto do momento para o botão "assistir ao trecho".
4. O estado do job fica **em memória no backend**, então o painel pode
   desconectar, recarregar ou trocar de aba que o progresso continua disponível
   via ``GET /api/offline/jobs``.

O registro ``_jobs`` é protegido por um lock e nunca perde o status por causa do
front-end: quem processa é o servidor, não o navegador.
"""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from app.core.config import get_settings
from app.domain.models import (
    CameraZones,
    OfflineDetectionOut,
    OfflineJobOut,
    ZoneConfig,
    ZoneMode,
)
from app.infra.ai.detector import Detection, get_bird_detector
from app.infra.ai.species_classifier import get_default_species_classifier
from app.infra.ai.zone_validator import point_in_polygon
from app.infra.database.repository import CameraRepository, VisitRepository
from app.infra.media.storage import (
    relative_to_captures,
    save_bird_crop,
    save_clip_mp4,
    save_thumbnail,
)
from app.services.calibration import get_calibration_service

logger = logging.getLogger(__name__)

# Limites de upload (mantidos em sincronia com o antigo fluxo de gravações).
MAX_RECORDING_BYTES = 2 * 1024 * 1024 * 1024
MAX_QUEUED_ANALYSES = 5
ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov"}

# --- Agregação de "aves distintas" ---------------------------------------- #
# Sobreposição mínima (IoU) para casar uma detecção a uma faixa já existente.
_IOU_MATCH = 0.10
# Distância máxima (normalizada) entre centros para casar a mesma ave quando o
# IoU é baixo (ave que se desloca rápido entre dois quadros analisados).
_MAX_CENTROID_DISTANCE = 0.22
# Observações mínimas para confirmar que a detecção é realmente uma ave.
_MIN_TRACK_OBSERVATIONS = 2
# Confiança mínima da melhor detecção da faixa para confirmá-la como ave.
_MIN_TRACK_CONFIDENCE = 0.30
# Janela de retenção (segundos de vídeo) para considerar a ave "presente"
# mesmo com detecções intermitentes (ave parada se alimentando).
_MAX_TRACK_RETENTION_SECONDS = 12.0
# Teto de aves distintas registradas por vídeo (proteção contra vídeos longos).
_MAX_BIRDS_PER_JOB = 250

# Atualiza o progresso no registro a cada N quadros processados.
_PROGRESS_EVERY = 8
# Mantém no máximo este número de jobs finalizados no histórico em memória.
_MAX_FINISHED_JOBS = 60


def _iou(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    """Interseção sobre união (IoU) entre duas caixas xyxy."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_w = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_h = max(0.0, min(ay2, by2) - max(ay1, by1))
    inter_area = inter_w * inter_h
    if inter_area <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area
    return inter_area / union if union > 0.0 else 0.0


def _media_url(relative: str | None) -> str | None:
    """Converte um caminho relativo a `captures/` em URL servida pela API."""
    if not relative:
        return None
    normalized = relative.replace("\\", "/").lstrip("/")
    if normalized.startswith("captures/"):
        return f"/{normalized}"
    return f"/captures/{normalized}"


@dataclass
class OfflineDetection:
    """Uma ave distinta identificada ao longo do vídeo."""

    id: str
    timestamp_seconds: float
    species: str
    confidence: float
    thumbnail_url: str | None = None
    crop_url: str | None = None
    visit_id: str | None = None

    def to_out(self) -> OfflineDetectionOut:
        return OfflineDetectionOut(
            id=self.id,
            timestamp_seconds=self.timestamp_seconds,
            species=self.species,
            confidence=self.confidence,
            thumbnail_url=self.thumbnail_url,
            crop_url=self.crop_url,
            visit_id=self.visit_id,
        )


@dataclass
class _Track:
    """Faixa em construção: uma ave que está sendo acompanhada no vídeo.

    Guarda apenas o índice do melhor quadro (não o quadro em si), evitando
    consumo de memória em vídeos longos. O quadro é relido no fim da análise.
    """

    bbox: tuple[float, float, float, float]
    class_name: str
    first_seen: float
    last_seen: float
    observations: int
    best_detection: Detection
    best_frame_index: int
    best_score: float


@dataclass
class _ConfirmedBird:
    """Ave confirmada, aguardando a materialização (miniatura/visita/clipe)."""

    detection: Detection
    frame_index: int
    first_seen: float
    last_seen: float
    score: float


@dataclass
class OfflineJob:
    """Estado completo de um upload/análise (mantido em memória no backend)."""

    id: str
    camera_id: str
    camera_name: str | None
    filename: str
    path: Path
    recorded_at: datetime
    status: Literal["queued", "processing", "completed", "error"] = "queued"
    progress: float = 0.0
    frames_processed: int = 0
    total_frames: int = 0
    progress_message: str = "Aguardando na fila de análise…"
    birds_detected_count: int = 0
    detections: list[OfflineDetection] = field(default_factory=list)
    summary: str | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    def to_out(self) -> OfflineJobOut:
        return OfflineJobOut(
            id=self.id,
            camera_id=self.camera_id,
            camera_name=self.camera_name,
            filename=self.filename,
            status=self.status,
            progress=min(100.0, max(0.0, self.progress)),
            frames_processed=self.frames_processed,
            total_frames=self.total_frames,
            progress_message=self.progress_message,
            birds_detected_count=self.birds_detected_count,
            detections=[detection.to_out() for detection in self.detections],
            summary=self.summary,
            error=self.error,
            created_at=self.created_at.isoformat().replace("+00:00", "Z"),
            finished_at=(
                self.finished_at.isoformat().replace("+00:00", "Z")
                if self.finished_at is not None
                else None
            ),
        )


class OfflineAnalysisService:
    """Orquestra uploads e análises offline em segundo plano (thread-safe)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="offline-analysis",
        )
        self._jobs: dict[str, OfflineJob] = {}
        self._futures: dict[str, Future[None]] = {}

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def submit(
        self,
        *,
        camera_id: str,
        camera_name: str | None,
        filename: str,
        path: Path,
        recorded_at: datetime,
    ) -> OfflineJobOut:
        """Registra um novo job e dispara a análise em background."""
        with self._lock:
            active_jobs = sum(
                job.status in {"queued", "processing"} for job in self._jobs.values()
            )
            if active_jobs >= MAX_QUEUED_ANALYSES:
                raise RuntimeError(
                    "A fila de análises está cheia. Aguarde a conclusão dos vídeos "
                    "em processamento."
                )
            job = OfflineJob(
                id=str(uuid.uuid4()),
                camera_id=camera_id,
                camera_name=camera_name,
                filename=filename,
                path=path,
                recorded_at=recorded_at.astimezone(timezone.utc),
            )
            self._jobs[job.id] = job
            self._prune()
            self._futures[job.id] = self._executor.submit(self._run_job, job.id)
            return job.to_out()

    def get(self, job_id: str) -> OfflineJobOut | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_out() if job else None

    def list_jobs(self) -> list[OfflineJobOut]:
        """Todos os jobs conhecidos, do mais recente ao mais antigo."""
        with self._lock:
            jobs = sorted(
                self._jobs.values(),
                key=lambda item: item.created_at,
                reverse=True,
            )
            return [job.to_out() for job in jobs]

    def delete(self, job_id: str) -> bool:
        """Remove um job já finalizado do histórico (não interrompe ativos)."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status in {"queued", "processing"}:
                return False
            self._jobs.pop(job_id, None)
            self._futures.pop(job_id, None)
            return True

    def clear_finished(self) -> int:
        """Remove todos os jobs finalizados e devolve a quantidade removida."""
        with self._lock:
            finished = [
                job_id
                for job_id, job in self._jobs.items()
                if job.status in {"completed", "error"}
            ]
            for job_id in finished:
                self._jobs.pop(job_id, None)
                self._futures.pop(job_id, None)
            return len(finished)

    def shutdown(self) -> None:
        with self._lock:
            queued = [
                (job_id, job.path)
                for job_id, job in self._jobs.items()
                if job.status == "queued"
                and self._futures.get(job_id) is not None
                and self._futures[job_id].cancel()
            ]
            for job_id, path in queued:
                self._jobs[job_id].status = "error"
                self._jobs[job_id].error = "Análise cancelada ao encerrar o backend."
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.exception("Could not remove cancelled upload job=%s", job_id)
        self._executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------ #
    # Registro / progresso
    # ------------------------------------------------------------------ #
    def _prune(self) -> None:
        """Limita o histórico de jobs finalizados (chamado com o lock ativo)."""
        finished = [
            job
            for job in self._jobs.values()
            if job.status in {"completed", "error"}
        ]
        if len(finished) <= _MAX_FINISHED_JOBS:
            return
        finished.sort(key=lambda item: item.created_at)
        for job in finished[: len(finished) - _MAX_FINISHED_JOBS]:
            self._jobs.pop(job.id, None)
            self._futures.pop(job.id, None)

    def _update(self, job_id: str, **fields: object) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                setattr(job, key, value)

    # ------------------------------------------------------------------ #
    # Geografia / zonas
    # ------------------------------------------------------------------ #
    @staticmethod
    def _load_camera_zones(camera_id: str) -> list[ZoneConfig]:
        settings = get_settings()
        row = CameraRepository(settings.db_path).get(camera_id)
        if row is None:
            raise ValueError("A câmera selecionada não existe mais.")
        return CameraZones.model_validate_json(
            row.get("zones_json") or '{"zones":[]}'
        ).zones

    @staticmethod
    def _frame_allowed(
        detection: Detection,
        width: int,
        height: int,
        zones: list[ZoneConfig],
    ) -> bool:
        center_x, center_y = detection.normalized_center(width, height)
        inclusions = [zone for zone in zones if zone.mode == ZoneMode.INCLUDE]
        if inclusions and not any(
            point_in_polygon(
                center_x,
                center_y,
                [(point.x, point.y) for point in zone.points],
            )
            for zone in inclusions
        ):
            return False
        return not any(
            point_in_polygon(
                center_x,
                center_y,
                [(point.x, point.y) for point in zone.points],
            )
            for zone in zones
            if zone.mode == ZoneMode.EXCLUDE
        )

    @staticmethod
    def _apply_zone_mask(frame: np.ndarray, zones: list[ZoneConfig]) -> np.ndarray:
        height, width = frame.shape[:2]
        mask = np.zeros((height, width), dtype=np.uint8)
        inclusions = [zone for zone in zones if zone.mode == ZoneMode.INCLUDE]
        if not inclusions:
            mask.fill(255)
        for zone in inclusions:
            points = np.array(
                [
                    [round(point.x * (width - 1)), round(point.y * (height - 1))]
                    for point in zone.points
                ],
                dtype=np.int32,
            )
            cv2.fillPoly(mask, [points], 255)
        for zone in zones:
            if zone.mode != ZoneMode.EXCLUDE:
                continue
            points = np.array(
                [
                    [round(point.x * (width - 1)), round(point.y * (height - 1))]
                    for point in zone.points
                ],
                dtype=np.int32,
            )
            cv2.fillPoly(mask, [points], 0)
        return cv2.bitwise_and(frame, frame, mask=mask)

    # ------------------------------------------------------------------ #
    # Detecção e agregação
    # ------------------------------------------------------------------ #
    @staticmethod
    def _score(detection: Detection, width: int, height: int) -> float:
        """Pontua uma detecção para escolher a melhor miniatura da ave.

        Prioriza a confiança, com um leve bônus para aves maiores na imagem
        (mais visíveis e fáceis de reconhecer).
        """
        x1, y1, x2, y2 = detection.bbox
        area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        area_ratio = area / max(1.0, float(width * height))
        return detection.confidence + min(area_ratio, 0.25)

    def _detect(
        self,
        frame: np.ndarray,
        zones: list[ZoneConfig],
        confidence: float,
        class_ids: list[int],
    ) -> list[Detection]:
        detector = get_bird_detector()
        masked = self._apply_zone_mask(frame, zones)
        height, width = frame.shape[:2]
        return [
            detection
            for detection in detector.detect(
                masked, confidence=confidence, class_ids=class_ids
            )
            if self._frame_allowed(detection, width, height, zones)
        ]

    def _associate(
        self,
        tracks: list[_Track],
        detections: list[Detection],
        source_seconds: float,
        frame_index: int,
        width: int,
        height: int,
        retention: float,
    ) -> list[_Track]:
        """Casa detecções com faixas existentes e devolve as faixas expiradas."""
        now = source_seconds
        matched: set[int] = set()

        for detection in detections:
            center_x, center_y = detection.normalized_center(width, height)
            best_index: int | None = None
            best_metric: float | None = None
            for index, track in enumerate(tracks):
                if index in matched:
                    continue
                iou = _iou(track.bbox, detection.bbox)
                track_x = (track.bbox[0] + track.bbox[2]) / 2.0 / max(width, 1)
                track_y = (track.bbox[1] + track.bbox[3]) / 2.0 / max(height, 1)
                distance = ((center_x - track_x) ** 2 + (center_y - track_y) ** 2) ** 0.5
                if iou < _IOU_MATCH and distance > _MAX_CENTROID_DISTANCE:
                    continue
                # Menor métrica = melhor casamento (IoU alto e centro próximo).
                metric = (1.0 - iou) + distance
                if best_metric is None or metric < best_metric:
                    best_metric = metric
                    best_index = index

            if best_index is None:
                tracks.append(
                    _Track(
                        bbox=detection.bbox,
                        class_name=detection.class_name,
                        first_seen=now,
                        last_seen=now,
                        observations=1,
                        best_detection=detection,
                        best_frame_index=frame_index,
                        best_score=self._score(detection, width, height),
                    )
                )
                continue

            matched.add(best_index)
            track = tracks[best_index]
            track.bbox = detection.bbox
            track.class_name = detection.class_name
            track.last_seen = now
            track.observations += 1
            score = self._score(detection, width, height)
            if score > track.best_score:
                track.best_score = score
                track.best_detection = detection
                track.best_frame_index = frame_index

        expired: list[_Track] = []
        remaining: list[_Track] = []
        for index, track in enumerate(tracks):
            if index in matched or now - track.last_seen <= retention:
                remaining.append(track)
            else:
                expired.append(track)
        tracks[:] = remaining
        return expired

    @staticmethod
    def _is_confirmed(track: _Track) -> bool:
        return (
            track.observations >= _MIN_TRACK_OBSERVATIONS
            and track.best_detection.confidence >= _MIN_TRACK_CONFIDENCE
        )

    # ------------------------------------------------------------------ #
    # Materialização (miniatura, visita e clipe)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _read_frame(capture: cv2.VideoCapture, index: int) -> np.ndarray | None:
        capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(index)))
        ok, frame = capture.read()
        return frame if ok and frame is not None and frame.size > 0 else None

    def _render_clip(
        self,
        capture: cv2.VideoCapture,
        center_index: int,
        fps: float,
        seconds: float,
        camera_id: str,
        visit_id: str,
    ) -> Path | None:
        """Gera um clipe curto ao redor da melhor captura da ave (best-effort)."""
        try:
            half = max(1, int(round(fps * seconds / 2.0)))
            start = max(0, int(center_index) - half)
            capture.set(cv2.CAP_PROP_POS_FRAMES, start)
            frames: list[np.ndarray] = []
            for _ in range(half * 2):
                ok, frame = capture.read()
                if not ok or frame is None or frame.size == 0:
                    break
                frames.append(frame)
            if len(frames) < 2:
                return None
            return save_clip_mp4(frames, camera_id, visit_id, fps)
        except Exception:
            logger.exception("Falha ao gerar o clipe offline visit=%s", visit_id)
            return None

    def _save_bird(
        self,
        *,
        job: OfflineJob,
        bird: _ConfirmedBird,
        frame: np.ndarray,
        fps: float,
        capture: cv2.VideoCapture,
        allow_clip: bool,
    ) -> OfflineDetection | None:
        settings = get_settings()
        detection = bird.detection
        visit_id = str(uuid.uuid4())

        try:
            prediction = get_default_species_classifier().classify(frame, detection.bbox)
            species = prediction.species
            extras = prediction.extras or {}
        except Exception:
            logger.exception("Falha ao classificar a espécie na análise offline")
            species = detection.class_name
            extras = {}

        thumbnail = save_thumbnail(frame, job.camera_id, visit_id)
        crop_path = save_bird_crop(frame, detection.bbox, visit_id)

        clip: Path | None = None
        if allow_clip:
            clip = self._render_clip(
                capture,
                bird.frame_index,
                fps,
                settings.offline_clip_seconds,
                job.camera_id,
                visit_id,
            )

        timestamp_seconds = round(bird.frame_index / fps, 3)
        detected_at = job.recorded_at + timedelta(seconds=timestamp_seconds)
        VisitRepository(settings.db_path).create(
            visit_id=visit_id,
            camera_id=job.camera_id,
            species=species,
            confidence=float(detection.confidence),
            detected_at=detected_at.isoformat().replace("+00:00", "Z"),
            dwell_seconds=float(max(0.0, bird.last_seen - bird.first_seen)),
            clip_path=relative_to_captures(clip) if clip is not None else None,
            thumbnail_path=(
                relative_to_captures(thumbnail) if thumbnail is not None else None
            ),
            bbox=detection.as_list(),
            zone_id="offline",
            metadata={
                "class_name": detection.class_name,
                "species_extras": extras,
                "crop_path": crop_path,
                "source": "offline_recording",
                "recording_filename": job.filename,
                "recording_analysis_id": job.id,
                "video_timestamp_seconds": timestamp_seconds,
            },
        )

        thumbnail_relative = (
            relative_to_captures(thumbnail) if thumbnail is not None else None
        )
        return OfflineDetection(
            id=visit_id,
            timestamp_seconds=timestamp_seconds,
            species=species,
            confidence=float(detection.confidence),
            thumbnail_url=_media_url(thumbnail_relative),
            crop_url=f"/api/visits/{visit_id}/crop" if crop_path else None,
            visit_id=visit_id,
        )

    # ------------------------------------------------------------------ #
    # Análise
    # ------------------------------------------------------------------ #
    @staticmethod
    def _progress_message(frames: int, total: int) -> str:
        if total > 0:
            return f"Processando frame {min(frames, total)}/{total}…"
        return f"Processando frame {frames}…"

    @staticmethod
    def _summary(count: int) -> str:
        if count == 0:
            return "Análise concluída: nenhuma ave foi detectada neste vídeo."
        if count == 1:
            return "Análise concluída: 1 pássaro detectado ao longo do vídeo."
        return (
            f"Análise concluída: foram detectados {count} pássaros distintos "
            "ao longo do vídeo."
        )

    def _process(self, job: OfflineJob) -> None:
        settings = get_settings()
        calibration = get_calibration_service().current()

        zones = [
            zone for zone in self._load_camera_zones(job.camera_id) if zone.enabled
        ]
        detector = get_bird_detector()
        if not detector.load():
            raise RuntimeError(
                detector.load_error or "O modelo YOLOv8 não pôde ser carregado."
            )

        # IA mais sensível: usa o menor limiar entre a calibração e o dedicado
        # à análise offline (padrão 0.25).
        confidence = min(
            float(calibration.yolo_confidence),
            float(settings.offline_yolo_confidence),
        )
        class_ids = [settings.yolo_bird_class_id]
        if calibration.night_fauna_enabled:
            class_ids.extend(settings.night_fauna_class_id_list())
        class_ids = sorted(set(class_ids))

        retention = min(
            _MAX_TRACK_RETENTION_SECONDS,
            max(3.0, float(calibration.object_persistence_time)),
        )
        stride = max(1, int(settings.offline_frame_stride))

        capture = cv2.VideoCapture(str(job.path))
        if not capture.isOpened():
            capture.release()
            raise ValueError("O arquivo não é um vídeo válido ou está corrompido.")
        try:
            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            if not np.isfinite(fps) or fps <= 0:
                fps = 25.0
            self._update(job.id, total_frames=max(0, total_frames))

            tracks: list[_Track] = []
            confirmed: list[_ConfirmedBird] = []
            frame_index = 0
            processed = 0
            saw_frame = False

            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame is None or frame.size == 0:
                    frame_index += 1
                    continue
                saw_frame = True

                if frame_index % stride == 0:
                    height, width = frame.shape[:2]
                    source_seconds = frame_index / fps
                    detections = self._detect(frame, zones, confidence, class_ids)
                    expired = self._associate(
                        tracks,
                        detections,
                        source_seconds,
                        frame_index,
                        width,
                        height,
                        retention,
                    )
                    for track in expired:
                        if self._is_confirmed(track):
                            confirmed.append(
                                _ConfirmedBird(
                                    detection=track.best_detection,
                                    frame_index=track.best_frame_index,
                                    first_seen=track.first_seen,
                                    last_seen=track.last_seen,
                                    score=track.best_score,
                                )
                            )
                    processed += 1
                    if processed % _PROGRESS_EVERY == 0:
                        progress = (
                            frame_index / total_frames * 100.0
                            if total_frames > 0
                            else 0.0
                        )
                        self._update(
                            job.id,
                            frames_processed=frame_index,
                            progress=min(progress, 99.0),
                            progress_message=self._progress_message(
                                frame_index, total_frames
                            ),
                        )

                frame_index += 1

            if not saw_frame:
                raise ValueError("O vídeo não contém quadros legíveis.")

            # Faixas que ainda estavam ativas no fim do vídeo.
            for track in tracks:
                if self._is_confirmed(track):
                    confirmed.append(
                        _ConfirmedBird(
                            detection=track.best_detection,
                            frame_index=track.best_frame_index,
                            first_seen=track.first_seen,
                            last_seen=track.last_seen,
                            score=track.best_score,
                        )
                    )

            # Ordena por instante no vídeo e limita a quantidade de aves.
            confirmed.sort(key=lambda item: item.frame_index)
            confirmed = confirmed[:_MAX_BIRDS_PER_JOB]

            max_clips = max(0, int(settings.offline_max_clips))
            detections_out: list[OfflineDetection] = []
            for index, bird in enumerate(confirmed):
                frame = self._read_frame(capture, bird.frame_index)
                if frame is None:
                    continue
                try:
                    detection = self._save_bird(
                        job=job,
                        bird=bird,
                        frame=frame,
                        fps=fps,
                        capture=capture,
                        allow_clip=index < max_clips,
                    )
                except Exception:
                    # Uma ave que falhe (ex.: câmera removida no meio da análise)
                    # não deve derrubar o resultado das demais.
                    logger.exception(
                        "Falha ao registrar uma ave na análise offline job=%s",
                        job.id,
                    )
                    detection = None
                if detection is not None:
                    detections_out.append(detection)
                self._update(
                    job.id,
                    progress=99.0,
                    progress_message=(
                        "Salvando capturas das aves "
                        f"({index + 1}/{len(confirmed)})…"
                    ),
                )

            detections_out.sort(key=lambda item: item.timestamp_seconds)
            count = len(detections_out)
            self._update(
                job.id,
                status="completed",
                progress=100.0,
                frames_processed=frame_index,
                total_frames=max(0, total_frames),
                detections=detections_out,
                birds_detected_count=count,
                summary=self._summary(count),
                progress_message="Análise concluída.",
                finished_at=datetime.now(timezone.utc),
            )
        finally:
            capture.release()

    # ------------------------------------------------------------------ #
    # Ciclo de vida do job
    # ------------------------------------------------------------------ #
    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "processing"
            job.progress_message = "Iniciando a análise do vídeo…"

        try:
            self._process(job)
        except Exception as exc:
            logger.exception("Falha na análise offline job=%s", job_id)
            message = (
                str(exc)
                if isinstance(exc, (ValueError, RuntimeError))
                else "Ocorreu um erro ao analisar o vídeo."
            )
            self._update(
                job_id,
                status="error",
                error=message,
                progress_message="A análise não pôde ser concluída.",
                finished_at=datetime.now(timezone.utc),
            )
        finally:
            path: Path | None
            with self._lock:
                current = self._jobs.get(job_id)
                path = current.path if current is not None else None
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.exception("Could not remove uploaded recording job=%s", job_id)


_service: OfflineAnalysisService | None = None
_service_lock = threading.Lock()


def get_offline_analysis_service() -> OfflineAnalysisService:
    global _service
    with _service_lock:
        if _service is None:
            _service = OfflineAnalysisService()
        return _service
