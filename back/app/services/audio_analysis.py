"""Background RTSP audio capture and BirdNET analysis."""

from __future__ import annotations

import importlib.util
import logging
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import numpy as np

from app.core.config import get_settings
from app.core.ffmpeg import get_ffmpeg_path
from app.domain.models import SourceType
from app.infra.camera.crypto import decrypt_secret
from app.infra.camera.streamer import CameraStreamer, StreamConfig
from app.infra.database.audio_repository import AudioDetectionRepository
from app.infra.database.repository import CameraRepository, SettingsRepository
from app.services.audio_devices import resolve_audio_input_args
from app.services.birdnet_runtime import available_runtime, ensure_tflite_runtime
from app.services.audio_clips import save_audio_clip
from app.services.stream_resolver import resolver_url_audio, resolver_url_direta

logger = logging.getLogger(__name__)

SAMPLE_RATE = 48_000
CHUNK_SECONDS = 3
CHUNK_BYTES = SAMPLE_RATE * 2 * CHUNK_SECONDS
MIN_CONFIDENCE = 0.70
STATUS_POLL_SECONDS = 2.0

_analyzer: Any | None = None
_analyzer_error: str | None = None
_analyzer_lock = threading.Lock()
_inference_lock = threading.Lock()

StatusCallback = Callable[[str, str, str], None]


def _audio_engine_issue() -> str | None:
    if get_ffmpeg_path() is None:
        return "FFmpeg não foi encontrado no PATH do sistema."
    if importlib.util.find_spec("birdnetlib") is None:
        return (
            "BirdNET não está instalado. Instale as dependências de bioacústica "
            "e reinicie o backend."
        )
    if available_runtime() is None:
        return (
            "O BirdNET precisa de um runtime TFLite. Instale 'ai-edge-litert' "
            "(recomendado) ou TensorFlow, compatível com este Python."
        )
    if importlib.util.find_spec("librosa") is None:
        return "A dependência librosa do BirdNET não está instalada."
    return None


def _get_analyzer() -> Any:
    global _analyzer, _analyzer_error
    with _analyzer_lock:
        if _analyzer is not None:
            return _analyzer
        if _analyzer_error is not None:
            raise RuntimeError(_analyzer_error)
        try:
            # Prepara o runtime TFLite (aplica o shim do ai-edge-litert quando
            # necessário) antes de importar o birdnetlib.
            if ensure_tflite_runtime() is None:
                raise RuntimeError("Nenhum runtime TFLite disponível para o BirdNET.")
            from birdnetlib.analyzer import Analyzer

            _analyzer = Analyzer()
        except Exception as exc:
            _analyzer_error = (
                "Não foi possível iniciar o BirdNET. Verifique o runtime TFLite "
                "(ai-edge-litert/TensorFlow) e os logs do backend."
            )
            logger.exception("BirdNET analyzer initialization failed")
            raise RuntimeError(_analyzer_error) from exc
        return _analyzer


def _read_chunk(stream: Any, size: int, stop_event: threading.Event) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining and not stop_event.is_set():
        part = stream.read(remaining)
        if not part:
            break
        chunks.append(part)
        remaining -= len(part)
    return b"".join(chunks)


def _read_detections(
    analyzer: Any,
    samples: bytes,
    min_confidence: float,
) -> list[dict[str, Any]]:
    from birdnetlib import RecordingBuffer

    audio_buffer = np.frombuffer(samples, dtype=np.int16).astype(np.float32)
    audio_buffer /= 32_768.0
    recording = RecordingBuffer(
        analyzer,
        audio_buffer,
        SAMPLE_RATE,
        min_conf=min_confidence - 1e-9,
    )
    with _inference_lock:
        recording.analyze()
    return [
        detection
        for detection in recording.detections
        if float(detection.get("confidence", 0.0)) >= min_confidence
    ]


def _is_non_bird_class(common_name: str, scientific_name: str) -> bool:
    """Indica se a detecção pertence a uma classe não-ave do BirdNET.

    O modelo global (6K) também reconhece classes como "Human vocal", "Noise",
    "Engine", "Dog", "Siren" e alguns insetos. Nessas classes o nome científico
    e o nome comum são idênticos (por exemplo, ``Dog_Dog``), enquanto as aves
    usam binomial de Lineu (por exemplo,
    ``Turdus rufiventris_Sabiá-laranjeira``). Como o Bem-Te-Vi é dedicado a
    aves, essas classes são descartadas antes da persistência.
    """
    return scientific_name.strip().casefold() == common_name.strip().casefold()


class AudioCameraWorker(threading.Thread):
    def __init__(
        self,
        camera_id: str,
        camera_name: str,
        on_status: StatusCallback,
    ) -> None:
        super().__init__(name=f"birdnet-{camera_id}", daemon=True)
        self.camera_id = camera_id
        self.camera_name = camera_name
        self._on_status = on_status
        self._stop_event = threading.Event()
        self._process: subprocess.Popen[bytes] | None = None
        self._process_lock = threading.Lock()
        settings = get_settings()
        self._camera_repo = CameraRepository(settings.db_path)
        self._settings_repo = SettingsRepository(settings.db_path)
        self._detection_repo = AudioDetectionRepository(settings.db_path)

    def stop(self) -> None:
        self._stop_event.set()
        self._stop_process()

    def _stop_process(self) -> None:
        with self._process_lock:
            process = self._process
            self._process = None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if process.stdout is not None:
            process.stdout.close()

    def _is_enabled(self) -> bool:
        value = self._settings_repo.get("audio_analysis_enabled", "false")
        return value.lower() in {"1", "true", "yes", "on"}

    def _confidence_threshold(self) -> float:
        value = self._settings_repo.get("audio_confidence_threshold")
        try:
            return min(1.0, max(MIN_CONFIDENCE, float(value or MIN_CONFIDENCE)))
        except ValueError:
            return MIN_CONFIDENCE

    def _audio_input_args(self) -> list[str]:
        """Argumentos de entrada do ffmpeg conforme a fonte de áudio.

        - Câmeras RTSP/ONVIF: captura o áudio do próprio stream.
        - Câmeras USB: captura de um dispositivo de entrada do sistema
          (microfone USB/webcam), definido em ``audio_input_device``.
        """
        row = self._camera_repo.get(self.camera_id)
        if row is None or not row["is_active"]:
            raise RuntimeError("Câmera indisponível ou desativada.")

        if row["source_type"] == SourceType.USB.value:
            device = self._settings_repo.get("audio_input_device", "") or None
            args = resolve_audio_input_args(device)
            logger.info(
                "Análise sonora: capturando áudio do dispositivo %s (câmera %s).",
                device or "padrão",
                row["name"],
            )
            return args

        config = StreamConfig(
            camera_id=row["id"],
            name=row["name"],
            source_type=SourceType(row["source_type"]),
            stream_url=row["stream_url"],
            username=decrypt_secret(row.get("username")),
            password=decrypt_secret(row.get("password_encrypted")),
            reconnect_delay_sec=2.0,
            backoff_base_sec=1.0,
            backoff_max_sec=30.0,
        )
        target = CameraStreamer(config).resolve_capture_target()
        if isinstance(target, str):
            # YouTube e outros links web: resolve para stream de áudio direto.
            target = resolver_url_audio(target)
        if not isinstance(target, str):
            raise RuntimeError(
                "A análise sonora exige uma câmera RTSP, ONVIF, HLS, HTTP ou um "
                "dispositivo de áudio USB."
            )
        if target.startswith("rtsp://") or target.startswith("rtsps://"):
            return ["-rtsp_transport", "tcp", "-i", target]
        elif target.startswith("http://") or target.startswith("https://"):
            return [
                "-headers",
                "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\r\nReferer: https://www.youtube.com/\r\n",
                "-i",
                target,
            ]
        return ["-i", target]

    def _open_audio_stream(self) -> subprocess.Popen[bytes]:
        input_args = self._audio_input_args()
        ffmpeg_bin = get_ffmpeg_path() or "ffmpeg"
        command = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-threads",
            "1",
            *input_args,
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "pipe:1",
        ]
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        with self._process_lock:
            self._process = process
        return process

    def _handle_chunk(
        self,
        samples: bytes,
        captured_at: datetime,
        analyzer: Any,
    ) -> None:
        min_confidence = self._confidence_threshold()
        detections = _read_detections(analyzer, samples, min_confidence)

        # O clipe de áudio do bloco é o mesmo para todas as detecções nele: grava
        # uma única vez (preguiçosamente) e reaproveita o caminho.
        bloco_gravado = False
        audio_path: str | None = None

        for detection in detections:
            common_name = str(detection.get("common_name") or "").strip()
            scientific_name = str(detection.get("scientific_name") or "").strip()
            if not common_name or not scientific_name:
                logger.warning(
                    "BirdNET returned an incomplete detection for camera %s",
                    self.camera_id,
                )
                continue
            if _is_non_bird_class(common_name, scientific_name):
                # Ruídos e vozes humanas não interessam a um app de aves.
                logger.debug(
                    "BirdNET: classe não-ave ignorada (%s) camera=%s",
                    common_name,
                    self.camera_id,
                )
                continue
            detection_offset = float(detection.get("start_time", 0.0))
            detected_at = captured_at + timedelta(
                seconds=max(0.0, min(float(CHUNK_SECONDS), detection_offset))
            )
            if not bloco_gravado:
                # O clipe de áudio da detecção (para o player da aba Detecção
                # Sonora). Falhas não impedem o registro da detecção.
                audio_path = save_audio_clip(samples)
                bloco_gravado = True
            result = self._detection_repo.create_and_link(
                camera_id=self.camera_id,
                detected_at=detected_at.isoformat(),
                species=common_name,
                scientific_name=scientific_name,
                confidence=float(detection["confidence"]),
                audio_path=audio_path,
            )
            logger.info(
                "BirdNET detection camera=%s species=%s confidence=%.3f linked_visit=%s",
                self.camera_id,
                scientific_name,
                float(detection["confidence"]),
                result["linked_visit_id"],
            )

    def run(self) -> None:
        self._on_status(self.camera_id, "starting", "Iniciando análise BirdNET.")
        while not self._stop_event.is_set():
            if not self._is_enabled():
                self._stop_process()
                self._on_status(
                    self.camera_id,
                    "starting",
                    "Aguardando a ativação da análise sonora.",
                )
                self._stop_event.wait(STATUS_POLL_SECONDS)
                continue

            engine_issue = _audio_engine_issue()
            if engine_issue:
                self._on_status(self.camera_id, "error", engine_issue)
                self._stop_event.wait(15)
                continue

            try:
                analyzer = _get_analyzer()
                process = self._open_audio_stream()
                if process.stdout is None:
                    raise RuntimeError("Não foi possível ler o áudio do stream.")
                received_audio = False
                while not self._stop_event.is_set() and self._is_enabled():
                    chunk_started_at = datetime.now(timezone.utc)
                    samples = _read_chunk(
                        process.stdout,
                        CHUNK_BYTES,
                        self._stop_event,
                    )
                    if len(samples) != CHUNK_BYTES:
                        if self._stop_event.is_set():
                            break
                        if not received_audio:
                            raise RuntimeError(
                                "O stream RTSP não fornece áudio ou está indisponível."
                            )
                        raise RuntimeError("O stream de áudio foi interrompido.")
                    received_audio = True
                    self._on_status(
                        self.camera_id,
                        "monitoring",
                        f"Analisando o áudio de {self.camera_name}.",
                    )
                    self._handle_chunk(samples, chunk_started_at, analyzer)
            except Exception as exc:
                message = str(exc)
                if "rtsp://" in message.lower():
                    message = "Não foi possível acessar o stream RTSP."
                self._on_status(self.camera_id, "error", message)
                logger.warning(
                    "Audio analysis failed camera=%s error_type=%s",
                    self.camera_id,
                    type(exc).__name__,
                )
                self._stop_event.wait(15)
            finally:
                self._stop_process()

        self._on_status(self.camera_id, "disabled", "Análise sonora parada.")


class AudioAnalysisService(threading.Thread):
    """Reconciles eligible RTSP cameras with their background audio workers."""

    def __init__(self) -> None:
        super().__init__(name="birdnet-supervisor", daemon=True)
        self.settings = get_settings()
        self.camera_repo = CameraRepository(self.settings.db_path)
        self.settings_repo = SettingsRepository(self.settings.db_path)
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._workers: dict[str, AudioCameraWorker] = {}
        self._worker_signatures: dict[str, str] = {}
        self._worker_status: dict[str, tuple[str, str]] = {}
        self._service_error: str | None = None

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
            self._worker_signatures.clear()
        for worker in workers:
            worker.stop()
        for worker in workers:
            worker.join(timeout=5)

    def _set_worker_status(self, camera_id: str, state: str, message: str) -> None:
        with self._lock:
            self._worker_status[camera_id] = (state, message)

    @staticmethod
    def _worker_signature(row: dict[str, Any], audio_input_device: str) -> str:
        """Assinatura que invalida o worker quando a fonte ou status de áudio muda."""
        base = f"{row.get('updated_at', '')}|audio_enabled={row.get('audio_enabled', 0)}"
        if row["source_type"] == SourceType.USB.value:
            return f"{base}|audio={audio_input_device}"
        return base

    def trigger_reconcile(self) -> None:
        """Força a sincronização imediata dos workers de áudio sem aguardar o polling."""
        try:
            self._reconcile()
        except Exception:
            logger.exception("Failed to trigger immediate BirdNET reconcile")

    def _reconcile(self) -> None:
        global_enabled_val = self.settings_repo.get("audio_analysis_enabled", "false")
        global_enabled = global_enabled_val.lower() in {"1", "true", "yes", "on"}
        rows = self.camera_repo.list_all()

        eligible: dict[str, dict[str, Any]] = {}
        usb_assigned = False
        for row in rows:
            if not row["is_active"]:
                continue
            audio_on = bool(row.get("audio_enabled", 0)) or global_enabled
            if not audio_on:
                continue
            source_type = row["source_type"]
            if source_type in {"rtsp", "onvif", "hls", "http", "webrtc"}:
                eligible[row["id"]] = row
            elif source_type == SourceType.USB.value and not usb_assigned:
                eligible[row["id"]] = row
                usb_assigned = True
        audio_input_device = self.settings_repo.get("audio_input_device", "") or ""
        with self._lock:
            stale_ids = {
                camera_id
                for camera_id in self._workers
                if camera_id not in eligible
                or self._worker_signatures.get(camera_id)
                != self._worker_signature(eligible[camera_id], audio_input_device)
            }
            stale = [self._workers.pop(camera_id) for camera_id in stale_ids]
            for camera_id in stale_ids:
                self._worker_signatures.pop(camera_id, None)
                self._worker_status.pop(camera_id, None)
            self._service_error = None
        for worker in stale:
            worker.stop()
            worker.join(timeout=5)
        with self._lock:
            for camera_id, row in eligible.items():
                if self._stop_event.is_set():
                    break
                worker = self._workers.get(camera_id)
                if worker is None or not worker.is_alive():
                    next_worker = AudioCameraWorker(
                        camera_id,
                        row["name"],
                        self._set_worker_status,
                    )
                    logger.info(
                        "Análise sonora: iniciando worker para câmera %s (fonte=%s).",
                        row["name"],
                        row["source_type"],
                    )
                    self._workers[camera_id] = next_worker
                    self._worker_signatures[camera_id] = self._worker_signature(
                        row, audio_input_device
                    )
                    self._worker_status[camera_id] = (
                        "starting",
                        "Aguardando análise do áudio.",
                    )
                    next_worker.start()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._reconcile()
            except Exception:
                self._service_error = (
                    "Falha ao sincronizar as câmeras para análise sonora."
                )
                logger.exception("Failed to reconcile BirdNET audio workers")
            self._stop_event.wait(STATUS_POLL_SECONDS)
        self.stop()

    def get_status(self, *, enabled: bool) -> dict[str, Any]:
        if not enabled:
            return {
                "enabled": False,
                "status": "disabled",
                "message": "Ative a análise sonora nas configurações para iniciar.",
                "monitored_cameras": 0,
            }

        engine_issue = _audio_engine_issue()
        if engine_issue:
            return {
                "enabled": True,
                "status": "error",
                "message": engine_issue,
                "monitored_cameras": 0,
            }

        with self._lock:
            if self._service_error:
                return {
                    "enabled": True,
                    "status": "error",
                    "message": self._service_error,
                    "monitored_cameras": 0,
                }
            states = list(self._worker_status.values())

        if not states:
            return {
                "enabled": True,
                "status": "no_cameras",
                "message": (
                    "Nenhuma câmera RTSP/ONVIF ou USB habilitada para análise."
                ),
                "monitored_cameras": 0,
            }

        monitoring_count = sum(state == "monitoring" for state, _ in states)
        if monitoring_count:
            status = "monitoring"
            if monitoring_count == len(states):
                message = f"Análise sonora ativa em {monitoring_count} câmera(s)."
            else:
                failed_message = next(
                    (
                        detail
                        for state, detail in states
                        if state == "error"
                    ),
                    "Verifique a conexão com as demais câmeras.",
                )
                message = (
                    f"Análise ativa em {monitoring_count} de {len(states)} câmera(s). "
                    f"{failed_message}"
                )
        elif all(state == "error" for state, _ in states):
            status = "error"
            message = states[0][1]
        else:
            status = "starting"
            message = "Conectando às câmeras e iniciando o BirdNET."
        return {
            "enabled": True,
            "status": status,
            "message": message,
            "monitored_cameras": monitoring_count,
        }


_service: AudioAnalysisService | None = None
_service_lock = threading.Lock()


def get_audio_analysis_service() -> AudioAnalysisService:
    global _service
    with _service_lock:
        if _service is None:
            _service = AudioAnalysisService()
        return _service
