"""Read-only queries used by habit analytics and the life list."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.infra.database.connection import db_session
from app.infra.database.repository import _media_url


class AnalyticsRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def summary(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        today_prefix = now.date().isoformat()
        week_start = (now - timedelta(days=7)).isoformat()

        with db_session(self.db_path) as conn:
            counts = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_visits,
                    SUM(CASE WHEN detected_at LIKE ? THEN 1 ELSE 0 END) AS visits_today,
                    SUM(CASE WHEN detected_at >= ? THEN 1 ELSE 0 END) AS visits_last_7_days,
                    COALESCE(AVG(dwell_seconds), 0) AS average_duration_seconds
                FROM visits
                """,
                (f"{today_prefix}%", week_start),
            ).fetchone()
            leader = conn.execute(
                """
                SELECT COALESCE(
                    bs.common_name,
                    NULLIF(v.species, 'bird'),
                    'Ave (genérica)'
                ) AS species_name, COUNT(*) AS visit_count
                FROM visits v
                LEFT JOIN bird_species bs ON bs.id = v.species_id
                GROUP BY species_name
                ORDER BY visit_count DESC, species_name COLLATE NOCASE ASC
                LIMIT 1
                """
            ).fetchone()
            peak = conn.execute(
                """
                SELECT substr(detected_at, 12, 2) AS hour, COUNT(*) AS visit_count
                FROM visits
                WHERE length(detected_at) >= 13
                GROUP BY hour
                ORDER BY visit_count DESC, hour ASC
                LIMIT 1
                """
            ).fetchone()

        return {
            "visits_today": int(counts["visits_today"] or 0),
            "visits_last_7_days": int(counts["visits_last_7_days"] or 0),
            "total_visits": int(counts["total_visits"] or 0),
            "most_frequent_species": leader["species_name"] if leader else None,
            "most_frequent_species_count": int(leader["visit_count"]) if leader else 0,
            "average_duration_seconds": float(counts["average_duration_seconds"] or 0),
            "peak_hour": f"{peak['hour']}h" if peak else None,
        }

    def hourly_distribution(self) -> list[dict[str, int | str]]:
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT substr(detected_at, 12, 2) AS hour, COUNT(*) AS visit_count
                FROM visits
                WHERE length(detected_at) >= 13
                GROUP BY hour
                """
            ).fetchall()

        counts = {str(row["hour"]): int(row["visit_count"]) for row in rows}
        return [
            {"hour": f"{hour:02d}", "visits": counts.get(f"{hour:02d}", 0)}
            for hour in range(24)
        ]

    def lifelist(self) -> list[dict[str, Any]]:
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    bs.id,
                    bs.common_name,
                    bs.scientific_name,
                    bs.description,
                    bs.reference_image_path,
                    bs.created_at,
                    COUNT(v.id) AS sightings_count,
                    MIN(v.detected_at) AS first_seen_at,
                    (
                        SELECT first_visit.thumbnail_path
                        FROM visits AS first_visit
                        WHERE first_visit.species_id = bs.id
                        ORDER BY first_visit.detected_at ASC, first_visit.id ASC
                        LIMIT 1
                    ) AS first_visit_thumbnail_path
                FROM bird_species bs
                LEFT JOIN visits v ON v.species_id = bs.id
                GROUP BY bs.id
                ORDER BY bs.common_name COLLATE NOCASE ASC
                """
            ).fetchall()

        result: list[dict[str, Any]] = []
        for row in rows:
            first_visit_photo = _media_url(row["first_visit_thumbnail_path"])
            reference_path = row["reference_image_path"]
            reference_image_url = (
                f"/reference-birds/{Path(reference_path).name}"
                if reference_path
                else None
            )
            result.append(
                {
                    "id": row["id"],
                    "common_name": row["common_name"],
                    "scientific_name": row["scientific_name"],
                    "description": row["description"] or "",
                    "is_unlocked": row["first_seen_at"] is not None,
                    "first_seen_at": row["first_seen_at"],
                    "featured_photo_url": first_visit_photo,
                    "reference_image_url": reference_image_url,
                    "sightings_count": int(row["sightings_count"]),
                }
            )
        return result
