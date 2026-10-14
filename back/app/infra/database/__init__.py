"""SQLite persistence adapters."""

from __future__ import annotations

import logging
from pathlib import Path

from app.core.config import get_settings
from app.infra.database.connection import close_all_connections, db_session, get_connection
from app.infra.database.migrations import apply_migrations
from app.infra.database.repository import (
    BirdSpeciesRepository,
    CameraRepository,
    SettingsRepository,
    VisitRepository,
)
from app.infra.database.audio_repository import AudioDetectionRepository

logger = logging.getLogger(__name__)


def init_database(db_path: Path | None = None) -> Path:
    settings = get_settings()
    path = db_path or settings.db_path
    settings.ensure_directories()
    conn = get_connection(path)
    version = apply_migrations(conn)
    logger.info("SQLite ready at %s (schema v%s)", path, version)
    return path


__all__ = [
    "AudioDetectionRepository",
    "CameraRepository",
    "BirdSpeciesRepository",
    "SettingsRepository",
    "VisitRepository",
    "close_all_connections",
    "db_session",
    "get_connection",
    "init_database",
]
