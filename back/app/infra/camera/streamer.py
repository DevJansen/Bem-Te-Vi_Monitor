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
    source_uri: str
    username: str | None = None
    password: str | None = None
    reconnect_delay_sec: float = 3.0
    read_timeout_sec: float = 10.0


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

    @property
    def status(self) -> StreamStatus:
        return self._status

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def fps(self) -> float:
        return max(self._fps, 1.0)

    def resolve_capture_target(self) -> str | int:
        st = self.config.source_type
        uri = self.config.source_uri.strip()

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

        # RTSP
        if uri.lower().startswith("rtsp://"):
            return build_rtsp_url(uri, username, password)
        return build_rtsp_url(uri, username, password)

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
        with self._lock:
            self._status = StreamStatus.CONNECTING
            self._release_unlocked()
            try:
                target = self.resolve_capture_target()
                self._opened_uri = self._redact(target)
                logger.info(
                    "Opening camera %s (%s) → %s",
                    self.config.camera_id,
                    self.config.name,
                    self._opened_uri,
                )
                if isinstance(target, int):
                    cap = cv2.VideoCapture(target, cv2.CAP_DSHOW)
                    if not cap.isOpened():
                        cap.release()
                        cap = cv2.VideoCapture(target)
                else:
                    cap = cv2.VideoCapture(target, cv2.CAP_FFMPEG)
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
        delay = min(
            self.config.reconnect_delay_sec * (1 + self._consecutive_failures),
            30.0,
        )
        time.sleep(delay)
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
            "source": self._opened_uri or self.config.source_uri,
        }
