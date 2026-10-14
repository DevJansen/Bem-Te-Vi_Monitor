"""Periodic local cleanup for expired video clips, snapshots and bird crops."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def cleanup_expired_media(
    settings: Settings | None = None,
    *,
    now: datetime | None = None,
) -> int:
    """Remove old media files only; SQLite visit/history rows are not touched."""
    settings = settings or get_settings()
    current_time = now or datetime.now(timezone.utc)
    cutoff = current_time.timestamp() - settings.media_retention_days * 86400
    media_dirs = (
        (settings.thumbs_dir, {".jpg", ".jpeg", ".png"}),
        (settings.crops_dir, {".jpg", ".jpeg", ".png"}),
        (settings.clips_dir, {".mp4", ".avi"}),
    )
    removed = 0

    for directory, extensions in media_dirs:
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if not path.is_file() or path.suffix.lower() not in extensions:
                continue
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed += 1
            except FileNotFoundError:
                continue
            except OSError:
                logger.exception("Failed to remove expired media file %s", path)

    if removed:
        logger.info("Removed %d expired media file(s)", removed)
    return removed


class MediaRetentionWorker:
    """Runs media retention immediately and then once per day."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="media-retention",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                cleanup_expired_media(self.settings)
            except Exception:
                logger.exception("Media retention cleanup failed")
            if self._stop.wait(24 * 60 * 60):
                return
