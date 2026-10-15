"""Read-only queries used by habit analytics and the life list."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.infra.database.connection import db_session
from app.infra.database.repository import _media_url, _optional_float
from app.services.weather_service import category_for_label


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

    def weather_correlation(self) -> dict[str, Any]:
        """Cruza a frequência de visitas com as condições meteorológicas.

        Agrupa as visitas por condição (rótulo pt-BR) e por categoria ampla
        (Ensolarado/Nublado/Chuva/...) e devolve os horários de pico com a
        temperatura média das visitas.
        """
        with db_session(self.db_path) as conn:
            totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_visits,
                    SUM(
                        CASE WHEN weather_code IS NOT NULL THEN 1 ELSE 0 END
                    ) AS visits_with_weather,
                    AVG(
                        CASE WHEN weather_code IS NOT NULL THEN temperature END
                    ) AS avg_temperature,
                    MIN(
                        CASE WHEN weather_code IS NOT NULL THEN temperature END
                    ) AS min_temperature,
                    MAX(
                        CASE WHEN weather_code IS NOT NULL THEN temperature END
                    ) AS max_temperature
                FROM visits
                """
            ).fetchone()
            condition_rows = conn.execute(
                """
                SELECT
                    weather_code AS condition,
                    COUNT(*) AS visits,
                    AVG(temperature) AS avg_temperature,
                    AVG(humidity) AS avg_humidity,
                    AVG(wind_speed) AS avg_wind_speed
                FROM visits
                WHERE weather_code IS NOT NULL
                GROUP BY weather_code
                ORDER BY visits DESC, weather_code COLLATE NOCASE ASC
                """
            ).fetchall()
            hour_rows = conn.execute(
                """
                SELECT
                    substr(detected_at, 12, 2) AS hour,
                    COUNT(*) AS visits,
                    AVG(temperature) AS avg_temperature
                FROM visits
                WHERE length(detected_at) >= 13
                GROUP BY hour
                ORDER BY visits DESC, hour ASC
                LIMIT 5
                """
            ).fetchall()

        by_condition: list[dict[str, Any]] = []
        category_accumulator: dict[str, dict[str, Any]] = {}
        for row in condition_rows:
            condition = row["condition"]
            visits = int(row["visits"])
            by_condition.append(
                {
                    "condition": condition,
                    "visits": visits,
                    "avg_temperature": _optional_float(row["avg_temperature"]),
                    "avg_humidity": _optional_float(row["avg_humidity"]),
                    "avg_wind_speed": _optional_float(row["avg_wind_speed"]),
                }
            )
            category = category_for_label(condition)
            bucket = category_accumulator.setdefault(
                category,
                {"condition": category, "visits": 0, "_weighted": 0.0, "_count": 0},
            )
            bucket["visits"] += visits
            temp = _optional_float(row["avg_temperature"])
            if temp is not None:
                bucket["_weighted"] += temp * visits
                bucket["_count"] += visits

        by_category = [
            {
                "condition": bucket["condition"],
                "visits": bucket["visits"],
                "avg_temperature": (
                    round(bucket["_weighted"] / bucket["_count"], 1)
                    if bucket["_count"]
                    else None
                ),
                "avg_humidity": None,
                "avg_wind_speed": None,
            }
            for bucket in sorted(
                category_accumulator.values(),
                key=lambda item: (-item["visits"], item["condition"]),
            )
        ]

        peak_hours = [
            {
                "hour": f"{row['hour']}h",
                "visits": int(row["visits"]),
                "avg_temperature": _optional_float(row["avg_temperature"]),
            }
            for row in hour_rows
            if row["hour"]
        ]

        return {
            "total_visits": int(totals["total_visits"] or 0),
            "visits_with_weather": int(totals["visits_with_weather"] or 0),
            "avg_temperature_on_visits": _optional_float(
                totals["avg_temperature"]
            ),
            "min_temperature_on_visits": _optional_float(
                totals["min_temperature"]
            ),
            "max_temperature_on_visits": _optional_float(
                totals["max_temperature"]
            ),
            "by_condition": by_condition,
            "by_category": by_category,
            "peak_hours": peak_hours,
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
