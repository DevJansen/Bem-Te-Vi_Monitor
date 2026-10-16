"""Versioned SQLite migrations for AviaWatch."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS cameras (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source_type TEXT NOT NULL CHECK (source_type IN ('usb', 'rtsp', 'onvif')),
            source_uri TEXT NOT NULL,
            username_enc TEXT,
            password_enc TEXT,
            enabled INTEGER NOT NULL DEFAULT 1,
            zones_json TEXT NOT NULL DEFAULT '{"zones":[]}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS visits (
            id TEXT PRIMARY KEY,
            camera_id TEXT NOT NULL,
            species TEXT NOT NULL DEFAULT 'bird',
            confidence REAL NOT NULL DEFAULT 0,
            detected_at TEXT NOT NULL,
            dwell_seconds REAL NOT NULL DEFAULT 0,
            clip_path TEXT,
            thumbnail_path TEXT,
            bbox_json TEXT,
            zone_id TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_visits_detected_at ON visits(detected_at DESC);
        CREATE INDEX IF NOT EXISTS idx_visits_camera_id ON visits(camera_id);
        CREATE INDEX IF NOT EXISTS idx_visits_species ON visits(species);

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """,
    ),
    (
        2,
        """
        CREATE TABLE IF NOT EXISTS bird_species (
            id TEXT PRIMARY KEY,
            common_name TEXT NOT NULL,
            scientific_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            reference_image_path TEXT,
            created_at TEXT NOT NULL
        );

        ALTER TABLE visits
        ADD COLUMN species_id TEXT REFERENCES bird_species(id) ON DELETE SET NULL;

        CREATE INDEX IF NOT EXISTS idx_visits_species_id ON visits(species_id);
        """,
    ),
    (
        3,
        """
        CREATE TABLE IF NOT EXISTS audio_detections (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL DEFAULT 'AUDIO_DETECTION'
                CHECK (event_type = 'AUDIO_DETECTION'),
            camera_id TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            species TEXT NOT NULL,
            scientific_name TEXT NOT NULL,
            confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            linked_visit_id TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE,
            FOREIGN KEY (linked_visit_id) REFERENCES visits(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_audio_detections_detected_at
            ON audio_detections(detected_at DESC);
        CREATE INDEX IF NOT EXISTS idx_audio_detections_camera_time
            ON audio_detections(camera_id, detected_at DESC);
        """,
    ),
    (
        4,
        """
        ALTER TABLE visits ADD COLUMN temperature REAL;
        ALTER TABLE visits ADD COLUMN humidity REAL;
        ALTER TABLE visits ADD COLUMN weather_code TEXT;
        ALTER TABLE visits ADD COLUMN wind_speed REAL;

        ALTER TABLE audio_detections ADD COLUMN temperature REAL;
        ALTER TABLE audio_detections ADD COLUMN humidity REAL;
        ALTER TABLE audio_detections ADD COLUMN weather_code TEXT;
        ALTER TABLE audio_detections ADD COLUMN wind_speed REAL;

        CREATE INDEX IF NOT EXISTS idx_visits_weather_code
            ON visits(weather_code);
        """,
    ),
    (
        5,
        """
        -- Status ecológico regional (avifauna do Sul do Brasil / SC) por espécie.
        ALTER TABLE bird_species ADD COLUMN ecological_status TEXT;

        -- Log de anomalias acústico-visuais (ex.: espécie ausente há meses).
        CREATE TABLE IF NOT EXISTS anomaly_events (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL DEFAULT 'species_return',
            created_at TEXT NOT NULL,
            species TEXT NOT NULL,
            scientific_name TEXT,
            days_absent INTEGER,
            message TEXT NOT NULL DEFAULT '',
            visit_id TEXT,
            acknowledged INTEGER NOT NULL DEFAULT 0,
            details_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_anomaly_events_created_at
            ON anomaly_events(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_anomaly_events_species
            ON anomaly_events(species);
        """,
    ),
]


def get_current_version(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute(
            "SELECT MAX(version) AS version FROM schema_migrations"
        ).fetchone()
        if row is None or row["version"] is None:
            return 0
        return int(row["version"])
    except sqlite3.OperationalError:
        return 0


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply pending migrations. Returns the final schema version."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    current = get_current_version(conn)
    applied = 0

    for version, sql in MIGRATIONS:
        if version <= current:
            continue
        logger.info("Applying database migration v%s", version)
        try:
            conn.executescript(sql)
            conn.execute(
                "INSERT OR REPLACE INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, _utc_now()),
            )
            conn.commit()
            applied += 1
            current = version
        except Exception:
            conn.rollback()
            logger.exception("Failed to apply migration v%s", version)
            raise

    if applied:
        logger.info("Database migrated to version %s (%s new)", current, applied)
    else:
        logger.debug("Database already at version %s", current)
    return current
