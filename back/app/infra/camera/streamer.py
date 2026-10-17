"""OpenCV capture with automatic reconnection for USB / RTSP streams."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse, urlunparse

import cv2
import numpy as np

from app.domain.models import SourceType
from app.infra.camera.onvif_helper import build_rtsp_url, resolve_onvif_rtsp
from app.services.stream_resolver import resolver_url_direta

logger = logging.getLogger(__name__)


class StreamStatus(str, Enum):
    IDLE = "idle"
    CONNECTING = "connecting"
    ONLINE = "online"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class StreamConfig:
    camera_id: str
    name: str
    source_type: SourceType
    stream_url: str
    username: str | None = None
    password: str | None = None
    reconnect_delay_sec: float = 3.0
    read_timeout_sec: float = 10.0
    # Backoff exponencial de reconexão (segundos).
    backoff_base_sec: float = 1.0
    backoff_max_sec: float = 30.0


@dataclass
class CameraStreamer:
    config: StreamConfig
    _cap: cv2.VideoCapture | None = field(default=None, init=False, repr=False)
    _status: StreamStatus = field(default=StreamStatus.IDLE, init=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False)
    _last_frame: np.ndarray | None = field(default=None, init=False, repr=False)
    _last_annotated_frame: np.ndarray | None = field(default=None, init=False, repr=False)
    _last_error: str | None = field(default=None, init=False)
    _fps: float = field(default=15.0, init=False)
    _opened_uri: str | None = field(default=None, init=False)
    _consecutive_failures: int = field(default=0, init=False)
    # Indica se o pipeline está entregando quadros em visão noturna (IR/baixa luz).
    _night_mode: bool = field(default=False, init=False)
    # Na próxima abertura, força a re-extração de links do YouTube (token expira).
    _forcar_resolver: bool = field(default=False, init=False)

    @property
    def status(self) -> StreamStatus:
        return self._status

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def night_mode(self) -> bool:
        """Se a câmera está com o realce de visão noturna ativo no momento."""
        return self._night_mode

    def set_night_mode(self, value: bool) -> None:
        """Publica o estado de visão noturna (chamado pelo pipeline)."""
        self._night_mode = bool(value)

    @property
    def fps(self) -> float:
        return max(self._fps, 1.0)

    def resolve_capture_target(self) -> str | int:
        """**Smart Stream Resolver**: decide o alvo de captura de forma inteligente.

        Regras:

        - **USB** → índice inteiro do dispositivo.
        - **ONVIF** → descobre a URL RTSP do dispositivo; se falhar, monta uma.
        - **HTTP/HLS/RTSP/WebRTC** → se houver usuário/senha cadastrados, injeta-os
          na URI em memória; se **não** houver (câmera pública/aberta), usa a URL
          crua exatamente como o usuário colou. Isso garante "colar o link e
          conectar" sem exigir credenciais.
        """
        st = self.config.source_type
        uri = self.config.stream_url.strip()

        if st == SourceType.USB:
            try:
                return int(uri)
            except ValueError:
                return uri

        username = self.config.username
        password = self.config.password

        if st == SourceType.ONVIF:
            discovered = resolve_onvif_rtsp(uri, username, password)
            if discovered:
                return discovered
            return build_rtsp_url(uri, username, password)

        # HTTP/HLS: o ffmpeg do OpenCV abre .m3u8 e URLs http(s) diretamente.
        if st in (SourceType.HTTP, SourceType.HLS):
            return self._inject_http_auth(uri, username, password)

        # RTSP (e WebRTC tratado como fluxo externo via ffmpeg, quando possível).
        # Sem credenciais, build_rtsp_url devolve a URL crua (link público).
        return build_rtsp_url(uri, username, password)

    @staticmethod
    def _inject_http_auth(
        uri: str, username: str | None, password: str | None
    ) -> str:
        """Injeta credenciais basic-auth em uma URL HTTP/HLS (em memória).

        Se a câmera for pública (sem usuário) ou a URL já trouxer credenciais,
        devolve a URL crua — preservando links abertos e evitando duplicação.
        """
        from urllib.parse import quote, urlparse, urlunparse

        parsed = urlparse(uri)
        if not username or parsed.username:
            return uri

        user = quote(username, safe="")
        pwd = quote(password or "", safe="")
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        netloc = f"{user}:{pwd}@{host}"
        return urlunparse(parsed._replace(netloc=netloc))

    @staticmethod
    def _redact(target: str | int) -> str:
        if isinstance(target, int):
            return f"usb:{target}"
        try:
            parsed = urlparse(str(target))
            if parsed.password:
                netloc = parsed.netloc.replace(f":{parsed.password}", ":****", 1)
                return urlunparse(parsed._replace(netloc=netloc))
        except Exception:
            pass
        return str(target)

    def open(self) -> bool:
        # 1) Resolve o alvo de captura FORA do lock: a tradução de links do
        #    YouTube (yt-dlp) e a descoberta ONVIF podem levar alguns segundos e
        #    não devem bloquear as leituras/streaming em andamento.
        forcar = self._forcar_resolver
        self._forcar_resolver = False
        try:
            target = self.resolve_capture_target()
            captura: str | int = target
            if isinstance(target, str):
                # Smart URL Resolver: traduz o link do YouTube para o stream
                # direto (m3u8/URL de mídia) antes de abrir. Na reconexão,
                # "forcar" re-extrai o link, pois o token da live expira.
                captura = resolver_url_direta(target, forcar=forcar)
            # Rótulo público (sem tokens) para logs/estado da câmera.
            rotulo = self._redact(target)
        except Exception as exc:
            with self._lock:
                self._status = StreamStatus.ERROR
                self._last_error = str(exc)
                self._consecutive_failures += 1
            logger.exception(
                "Error resolving capture target for camera %s", self.config.camera_id
            )
            return False

        # 2) Abre a captura com o alvo já resolvido.
        with self._lock:
            self._status = StreamStatus.CONNECTING
            self._release_unlocked()
            try:
                self._opened_uri = rotulo
                logger.info(
                    "Opening camera %s (%s) → %s",
                    self.config.camera_id,
                    self.config.name,
                    rotulo,
                )
                if isinstance(captura, int):
                    cap = cv2.VideoCapture(captura, cv2.CAP_DSHOW)
                    if not cap.isOpened():
                        cap.release()
                        cap = cv2.VideoCapture(captura)
                else:
                    cap = cv2.VideoCapture(captura, cv2.CAP_FFMPEG)
                    try:
                        cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)
                    except Exception:
                        pass

                if not cap.isOpened():
                    self._status = StreamStatus.ERROR
                    self._last_error = "Failed to open capture"
                    self._consecutive_failures += 1
                    return False

                fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
                self._fps = fps if fps > 1 else 15.0
                self._cap = cap
                self._status = StreamStatus.ONLINE
                self._last_error = None
                self._consecutive_failures = 0
                return True
            except Exception as exc:
                self._status = StreamStatus.ERROR
                self._last_error = str(exc)
                self._consecutive_failures += 1
                logger.exception(
                    "Error opening camera %s", self.config.camera_id
                )
                return False

    def _release_unlocked(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def close(self) -> None:
        with self._lock:
            self._release_unlocked()
            self._status = StreamStatus.STOPPED

    def reconnect(self) -> bool:
        with self._lock:
            self._status = StreamStatus.RECONNECTING
            self._release_unlocked()
            # Na reconexão, re-extrai o link direto (tokens de live do YouTube
            # expiram após algumas horas). Sem efeito para fontes não-YouTube.
            self._forcar_resolver = True
        # Backoff exponencial: dobra a cada falha, limitado ao teto configurado.
        atraso = min(
            self.config.backoff_base_sec * (2 ** self._consecutive_failures),
            self.config.backoff_max_sec,
        )
        time.sleep(atraso)
        return self.open()

    def read(self) -> tuple[bool, np.ndarray | None]:
        with self._lock:
            if self._cap is None or not self._cap.isOpened():
                return False, None
            try:
                ok, frame = self._cap.read()
            except Exception as exc:
                self._last_error = str(exc)
                self._status = StreamStatus.ERROR
                logger.exception("Read failed for camera %s", self.config.camera_id)
                return False, None

            if not ok or frame is None:
                self._consecutive_failures += 1
                self._status = StreamStatus.ERROR
                self._last_error = "Empty frame"
                return False, None

            self._last_frame = frame
            self._status = StreamStatus.ONLINE
            self._consecutive_failures = 0
            return True, frame

    def get_latest_frame(self) -> np.ndarray | None:
        with self._lock:
            if self._last_frame is None:
                return None
            return self._last_frame.copy()

    def set_annotated_frame(self, frame: np.ndarray | None) -> None:
        """Publica o frame com bounding boxes para o stream MJPEG."""
        with self._lock:
            if frame is None:
                self._last_annotated_frame = None
            else:
                self._last_annotated_frame = frame.copy()

    def get_latest_annotated_frame(self) -> np.ndarray | None:
        with self._lock:
            if self._last_annotated_frame is not None:
                return self._last_annotated_frame.copy()
            if self._last_frame is None:
                return None
            return self._last_frame.copy()

    def snapshot_jpeg(
        self,
        quality: int = 80,
        *,
        annotated: bool = False,
    ) -> bytes | None:
        frame = (
            self.get_latest_annotated_frame()
            if annotated
            else self.get_latest_frame()
        )
        if frame is None:
            return None
        try:
            ok, buf = cv2.imencode(
                ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            )
            if not ok:
                return None
            return buf.tobytes()
        except Exception:
            logger.exception("JPEG encode failed for camera %s", self.config.camera_id)
            return None

    def info(self) -> dict[str, Any]:
        return {
            "camera_id": self.config.camera_id,
            "name": self.config.name,
            "status": self._status.value,
            "fps": self.fps,
            "last_error": self._last_error,
            "source": self._opened_uri or self.config.stream_url,
            "night_mode": self._night_mode,
        }
