"""Persistence for BirdNET audio detections."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.infra.database.connection import db_session


class AudioDetectionRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def create_and_link(
        self,
        *,
        camera_id: str,
        detected_at: str,
        species: str,
        scientific_name: str,
        confidence: float,
    ) -> dict[str, Any]:
        detection_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with db_session(self.db_path) as conn:
            linked_visit = conn.execute(
                """
                SELECT id
                FROM visits
                WHERE camera_id = ?
                    AND ABS(
                        (julianday(detected_at) - julianday(?)) * 86400.0
                    ) <= 30
                ORDER BY ABS(
                    (julianday(detected_at) - julianday(?)) * 86400.0
                ), detected_at DESC
                LIMIT 1
                """,
                (camera_id, detected_at, detected_at),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO audio_detections (
                    id, event_type, camera_id, detected_at, species,
                    scientific_name, confidence, linked_visit_id, created_at
                ) VALUES (?, 'AUDIO_DETECTION', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    detection_id,
                    camera_id,
                    detected_at,
                    species,
                    scientific_name,
                    confidence,
                    linked_visit["id"] if linked_visit else None,
                    created_at,
                ),
            )
            row = conn.execute(
                """
                SELECT ad.*, c.name AS camera_name
                FROM audio_detections ad
                JOIN cameras c ON c.id = ad.camera_id
                WHERE ad.id = ?
                """,
                (detection_id,),
            ).fetchone()
            if row is None:
                raise RuntimeError("A detecção de áudio não foi persistida.")
            return dict(row)

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT ad.*, c.name AS camera_name
                FROM audio_detections ad
                JOIN cameras c ON c.id = ad.camera_id
                ORDER BY ad.detected_at DESC, ad.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
