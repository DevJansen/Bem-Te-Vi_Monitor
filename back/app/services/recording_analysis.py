"""Background processing of uploaded local video recordings."""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from app.core.config import get_settings
from app.domain.models import (
    CameraZones,
    RecordingAnalysisOut,
    ZoneConfig,
    ZoneMode,
)
from app.infra.ai.detector import Detection, get_bird_detector
from app.infra.ai.species_classifier import get_default_species_classifier
from app.infra.ai.zone_validator import ZoneValidator, point_in_polygon
from app.infra.database.repository import CameraRepository, VisitRepository
from app.infra.media.storage import relative_to_captures, save_bird_crop, save_thumbnail
from app.services.calibration import get_calibration_service

logger = logging.getLogger(__name__)

MAX_RECORDING_BYTES = 2 * 1024 * 1024 * 1024
MAX_QUEUED_ANALYSES = 5
ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mkv"}


@dataclass
class AnalysisJob:
    id: str
    camera_id: str
    filename: str
    path: Path
    recorded_at: datetime
    status: Literal["queued", "processing", "completed", "failed"] = "queued"
    progress: float = 0.0
    visits_created: int = 0
    error: str | None = None

    def to_out(self) -> RecordingAnalysisOut:
        return RecordingAnalysisOut(
            id=self.id,
            camera_id=self.camera_id,
            filename=self.filename,
            status=self.status,
            progress=self.progress,
            visits_created=self.visits_created,
            error=self.error,
        )


class RecordingAnalysisService:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="recording-analysis",
        )
        self._jobs: dict[str, AnalysisJob] = {}
        self._futures: dict[str, Future[None]] = {}

    def submit(
        self,
        *,
        camera_id: str,
        filename: str,
        path: Path,
        recorded_at: datetime,
    ) -> RecordingAnalysisOut:
        with self._lock:
            active_jobs = sum(
                job.status in {"queued", "processing"} for job in self._jobs.values()
            )
            if active_jobs >= MAX_QUEUED_ANALYSES:
                raise RuntimeError("A fila de análises está cheia. Tente novamente mais tarde.")
            job = AnalysisJob(
                id=str(uuid.uuid4()),
                camera_id=camera_id,
                filename=filename,
                path=path,
                recorded_at=recorded_at.astimezone(timezone.utc),
            )
            self._jobs[job.id] = job
            self._prune_jobs()
            self._futures[job.id] = self._executor.submit(self._run_job, job.id)
            return job.to_out()

    def get(self, job_id: str) -> RecordingAnalysisOut | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.to_out() if job else None

    def _prune_jobs(self) -> None:
        terminal_jobs = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in {"completed", "failed"}
        ]
        for job_id in terminal_jobs[:-50]:
            self._jobs.pop(job_id, None)
            self._futures.pop(job_id, None)

    def _update(
        self,
        job_id: str,
        *,
        status: Literal["queued", "processing", "completed", "failed"] | None = None,
        progress: float | None = None,
        visits_created: int | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            if status is not None:
                job.status = status
            if progress is not None:
                maximum = 100.0 if status == "completed" else 99.0
                job.progress = min(maximum, max(0.0, progress))
            if visits_created is not None:
                job.visits_created = visits_created
            if error is not None:
                job.error = error

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

    def _save_visit(
        self,
        *,
        job: AnalysisJob,
        frame: np.ndarray,
        detection: Detection,
        trigger_zone_id: str,
        dwell_seconds: float,
        detected_at: datetime,
    ) -> None:
        settings = get_settings()
        repository = VisitRepository(settings.db_path)
        visit_id = str(uuid.uuid4())
        prediction = get_default_species_classifier().classify(frame, detection.bbox)
        thumbnail = save_thumbnail(frame, job.camera_id, visit_id)
        crop_path = save_bird_crop(frame, detection.bbox, visit_id)
        thumbnail_relative = (
            relative_to_captures(thumbnail) if thumbnail is not None else None
        )
        repository.create(
            visit_id=visit_id,
            camera_id=job.camera_id,
            species=prediction.species,
            confidence=float(detection.confidence),
            detected_at=detected_at.isoformat().replace("+00:00", "Z"),
            dwell_seconds=float(dwell_seconds),
            clip_path=None,
            thumbnail_path=thumbnail_relative,
            bbox=detection.as_list(),
            zone_id=trigger_zone_id,
            metadata={
                "class_name": detection.class_name,
                "species_extras": prediction.extras or {},
                "crop_path": crop_path,
                "source": "offline_recording",
                "recording_filename": job.filename,
                "recording_analysis_id": job.id,
            },
        )

    def _process(self, job: AnalysisJob) -> int:
        settings = get_settings()
        zones = [zone for zone in self._load_camera_zones(job.camera_id) if zone.enabled]
        include_zones = [zone for zone in zones if zone.mode == ZoneMode.INCLUDE]
        validator = ZoneValidator(include_zones)
        detector = get_bird_detector()
        if not detector.load():
            raise RuntimeError(
                detector.load_error or "O modelo YOLOv8 não pôde ser carregado."
            )
        # Usa o mesmo limiar calibrado da análise ao vivo (menor = mais sensível),
        # permitindo encontrar aves imóveis se alimentando também nos vídeos.
        detector.set_confidence(get_calibration_service().current().yolo_confidence)

        capture = cv2.VideoCapture(str(job.path))
        if not capture.isOpened():
            capture.release()
            raise ValueError("O arquivo não é um vídeo válido ou está corrompido.")
        try:
            total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = float(capture.get(cv2.CAP_PROP_FPS))
            if not np.isfinite(fps) or fps <= 0:
                fps = 25.0

            frame_index = 0
            visits_created = 0
            saw_frame = False
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame is None or frame.size == 0:
                    frame_index += 1
                    continue
                saw_frame = True
                height, width = frame.shape[:2]
                detections = [
                    detection
                    for detection in detector.detect(self._apply_zone_mask(frame, zones))
                    if self._frame_allowed(detection, width, height, zones)
                ]
                source_seconds = frame_index / fps
                centers = [
                    detection.normalized_center(width, height)
                    for detection in detections
                ]
                triggers = validator.update(centers, now=source_seconds)
                for trigger in triggers[:1]:
                    eligible = [
                        detection
                        for detection in detections
                        if self._frame_allowed(detection, width, height, zones)
                        and (
                            trigger.zone_id == "full_frame"
                            or any(
                                zone.id == trigger.zone_id
                                and point_in_polygon(
                                    *detection.normalized_center(width, height),
                                    [(point.x, point.y) for point in zone.points],
                                )
                                for zone in include_zones
                            )
                        )
                    ]
                    if not eligible:
                        continue
                    detection = max(eligible, key=lambda item: item.confidence)
                    self._save_visit(
                        job=job,
                        frame=frame,
                        detection=detection,
                        trigger_zone_id=trigger.zone_id,
                        dwell_seconds=trigger.dwell_seconds,
                        detected_at=job.recorded_at + timedelta(seconds=source_seconds),
                    )
                    visits_created += 1

                frame_index += 1
                if frame_index % 10 == 0 or (
                    total_frames > 0 and frame_index >= total_frames
                ):
                    self._update(
                        job.id,
                        progress=(
                            frame_index / total_frames * 100
                            if total_frames > 0
                            else None
                        ),
                        visits_created=visits_created,
                    )

            if not saw_frame:
                raise ValueError("O vídeo não contém quadros legíveis.")
            return visits_created
        finally:
            capture.release()

    def _run_job(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "processing"
        try:
            visits_created = self._process(job)
            self._update(
                job_id,
                status="completed",
                progress=100,
                visits_created=visits_created,
            )
        except Exception as exc:
            logger.exception("Offline video analysis failed job=%s", job_id)
            message = str(exc) if isinstance(exc, (ValueError, RuntimeError)) else (
                "Ocorreu um erro ao analisar o vídeo."
            )
            self._update(job_id, status="failed", error=message)
        finally:
            try:
                job.path.unlink(missing_ok=True)
            except OSError:
                logger.exception("Could not remove uploaded recording job=%s", job_id)

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
                self._jobs[job_id].status = "failed"
                self._jobs[job_id].error = "Análise cancelada ao encerrar o backend."
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.exception("Could not remove cancelled upload job=%s", job_id)
        self._executor.shutdown(wait=False, cancel_futures=True)


_service: RecordingAnalysisService | None = None
_service_lock = threading.Lock()


def get_recording_analysis_service() -> RecordingAnalysisService:
    global _service
    with _service_lock:
        if _service is None:
            _service = RecordingAnalysisService()
        return _service
