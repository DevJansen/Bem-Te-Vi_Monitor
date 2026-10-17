"""Manages camera streamer lifecycle across the application."""

from __future__ import annotations

import logging
import threading
from typing import Any

from app.core.config import get_settings
from app.domain.models import SourceType
from app.infra.camera.crypto import decrypt_secret
from app.infra.camera.streamer import CameraStreamer, StreamConfig, StreamStatus
from app.infra.database.repository import CameraRepository

logger = logging.getLogger(__name__)


class CameraManager:
    def __init__(self) -> None:
        self._streamers: dict[str, CameraStreamer] = {}
        self._lock = threading.RLock()
        self._settings = get_settings()
        self._repo = CameraRepository(self._settings.db_path)

    def status_map(self) -> dict[str, str]:
        with self._lock:
            return {
                cid: s.status.value for cid, s in self._streamers.items()
            }

    def get_streamer(self, camera_id: str) -> CameraStreamer | None:
        with self._lock:
            return self._streamers.get(camera_id)

    def get_status(self, camera_id: str) -> str:
        with self._lock:
            streamer = self._streamers.get(camera_id)
            if streamer is None:
                row = self._repo.get(camera_id)
                if row and not row["is_active"]:
                    return "disabled"
                return "idle"
            return streamer.status.value

    def get_night_mode(self, camera_id: str) -> bool:
        """Informa se a câmera está com o realce de visão noturna ativo."""
        with self._lock:
            streamer = self._streamers.get(camera_id)
            return bool(streamer.night_mode) if streamer is not None else False

    def _row_to_config(self, row: dict[str, Any]) -> StreamConfig:
        return StreamConfig(
            camera_id=row["id"],
            name=row["name"],
            source_type=SourceType(row["source_type"]),
            stream_url=row["stream_url"],
            username=decrypt_secret(row.get("username")),
            password=decrypt_secret(row.get("password_encrypted")),
            reconnect_delay_sec=self._settings.camera_reconnect_delay_sec,
            backoff_base_sec=self._settings.camera_backoff_base_sec,
            backoff_max_sec=self._settings.camera_backoff_max_sec,
        )

    def upsert_streamer(self, camera_id: str) -> CameraStreamer | None:
        row = self._repo.get(camera_id)
        if row is None:
            self.remove_streamer(camera_id)
            return None

        with self._lock:
            existing = self._streamers.get(camera_id)
            if existing is not None:
                existing.close()

            if not row["is_active"]:
                self._streamers.pop(camera_id, None)
                return None

            streamer = CameraStreamer(self._row_to_config(row))
            self._streamers[camera_id] = streamer
            return streamer

    def remove_streamer(self, camera_id: str) -> None:
        with self._lock:
            streamer = self._streamers.pop(camera_id, None)
            if streamer is not None:
                streamer.close()

    def load_enabled(self) -> list[CameraStreamer]:
        loaded: list[CameraStreamer] = []
        for row in self._repo.list_all():
            if not row["is_active"]:
                continue
            streamer = self.upsert_streamer(row["id"])
            if streamer is not None:
                loaded.append(streamer)
        return loaded

    def shutdown(self) -> None:
        with self._lock:
            for streamer in self._streamers.values():
                try:
                    streamer.close()
                except Exception:
                    logger.exception("Error closing streamer")
            self._streamers.clear()

    def list_info(self) -> list[dict[str, Any]]:
        with self._lock:
            return [s.info() for s in self._streamers.values()]


_camera_manager: CameraManager | None = None
_manager_lock = threading.Lock()


def get_camera_manager() -> CameraManager:
    global _camera_manager
    with _manager_lock:
        if _camera_manager is None:
            _camera_manager = CameraManager()
        return _camera_manager
