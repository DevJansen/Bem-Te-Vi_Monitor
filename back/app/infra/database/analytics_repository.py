"""Read-only queries used by habit analytics and the life list."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.infra.database.connection import db_session
from app.infra.database.repository import _media_url, _optional_float
from app.domain.avifauna_sul import descrever
from app.services.weather_service import category_for_label

# Limiares de raridade (por número de avistagens da espécie no histórico local).
# 1-2 avistagens: Rara · 3-9: Incomum · 10+: Comum.
RARITY_RARE_MAX = 2
RARITY_UNCOMMON_MAX = 9


def _rarity_for_sightings(sightings: int) -> str:
    """Classifica a raridade de uma espécie a partir do nº de avistagens."""
    if sightings <= 0:
        return "Não observada"
    if sightings <= RARITY_RARE_MAX:
        return "Rara"
    if sightings <= RARITY_UNCOMMON_MAX:
        return "Incomum"
    return "Comum"


def _species_badges(sightings: int, rarity: str) -> list[str]:
    """Medalhas/marcos exibidos no card de cada espécie do álbum."""
    badges: list[str] = []
    if sightings > 0:
        badges.append("Primeira Vez")
    if rarity == "Rara":
        badges.append("Ave Rara")
    if sightings >= 10:
        badges.append("Espécie Fiel")
    if sightings >= 50:
        badges.append("Superstar")
    return badges


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

    def total_visits(self) -> int:
        """Número total de visitas registradas (todas as colunas do histórico)."""
        with db_session(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM visits").fetchone()
        return int(row["c"]) if row else 0

    def weather_visit_rows(self) -> list[dict[str, Any]]:
        """Visitas que têm algum dado meteorológico registrado.

        Traz apenas as colunas necessárias para os insights de clima e hábitos
        (data/hora, temperatura, umidade, condição e espécie resolvida). A
        agregação estatística fica em ``app.services.weather_insights``.
        """
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    v.detected_at,
                    v.temperature,
                    v.humidity,
                    v.weather_code,
                    COALESCE(
                        bs.common_name,
                        NULLIF(v.species, 'bird'),
                        'Ave (genérica)'
                    ) AS species_name,
                    bs.scientific_name AS scientific_name
                FROM visits v
                LEFT JOIN bird_species bs ON bs.id = v.species_id
                WHERE v.temperature IS NOT NULL OR v.weather_code IS NOT NULL
                ORDER BY v.detected_at ASC
                """
            ).fetchall()
        return [dict(row) for row in rows]

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
                    ) AS first_visit_thumbnail_path,
                    (
                        SELECT best.thumbnail_path
                        FROM visits AS best
                        WHERE best.species_id = bs.id
                            AND best.thumbnail_path IS NOT NULL
                        ORDER BY best.confidence DESC, best.detected_at DESC
                        LIMIT 1
                    ) AS best_photo_path
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
            sightings = int(row["sightings_count"])
            rarity = _rarity_for_sightings(sightings)
            status_ecologico = descrever(
                common_name=row["common_name"],
                scientific_name=row["scientific_name"],
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
                    "sightings_count": sightings,
                    # Campos gamificados do álbum de figurinhas.
                    "visits_count": sightings,
                    "rarity": rarity,
                    "best_photo_url": _media_url(row["best_photo_path"]),
                    "badges": _species_badges(sightings, rarity),
                    # Status ecológico regional (base do Sul do Brasil / SC).
                    "ecological_status": status_ecologico["status"],
                    "ecological_status_label": status_ecologico["label"],
                    "ecological_badge": status_ecologico["badge"],
                }
            )
        return result

    def achievements(self) -> list[dict[str, Any]]:
        """Medalhas/marcos globais conquistados pelo observador.

        Cada conquista devolve o progresso atual e o alvo, permitindo que o
        front-end desenhe a barra de progresso e o estado bloqueado/desbloqueado.
        """
        with db_session(self.db_path) as conn:
            totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_visits,
                    COUNT(DISTINCT species_id) AS species_observed,
                    COUNT(DISTINCT substr(detected_at, 1, 10)) AS active_days
                FROM visits
                """
            ).fetchone()
            dawn_count = conn.execute(
                """
                SELECT COUNT(*) AS c FROM visits
                WHERE length(detected_at) >= 13
                    AND CAST(substr(detected_at, 12, 2) AS INTEGER) < 6
                """
            ).fetchone()["c"]
            night_count = conn.execute(
                """
                SELECT COUNT(*) AS c FROM visits
                WHERE length(detected_at) >= 13
                    AND CAST(substr(detected_at, 12, 2) AS INTEGER) >= 20
                """
            ).fetchone()["c"]
            rain_count = conn.execute(
                """
                SELECT COUNT(*) AS c FROM visits
                WHERE weather_code LIKE '%Chuva%'
                    OR weather_code LIKE '%Chuvisco%'
                    OR weather_code LIKE '%Pancada%'
                    OR weather_code LIKE '%Tempestade%'
                """
            ).fetchone()["c"]
            rare_count = conn.execute(
                """
                SELECT COUNT(*) AS c FROM (
                    SELECT species_id FROM visits
                    WHERE species_id IS NOT NULL
                    GROUP BY species_id
                    HAVING COUNT(*) BETWEEN 1 AND ?
                )
                """,
                (RARITY_RARE_MAX,),
            ).fetchone()["c"]

        total_visits = int(totals["total_visits"] or 0)
        species_observed = int(totals["species_observed"] or 0)
        active_days = int(totals["active_days"] or 0)
        dawn_count = int(dawn_count or 0)
        night_count = int(night_count or 0)
        rain_count = int(rain_count or 0)
        rare_count = int(rare_count or 0)

        # (id, nome, descrição, ícone, alvo, progresso atual)
        definitions: list[tuple[str, str, str, str, int, int]] = [
            (
                "primeira_visita",
                "Primeira Visita",
                "Registre a primeira ave no alimentador.",
                "🐣",
                1,
                total_visits,
            ),
            (
                "explorador",
                "Explorador",
                "Descubra 3 espécies diferentes.",
                "🔭",
                3,
                species_observed,
            ),
            (
                "colecionador",
                "Colecionador",
                "Descubra 5 espécies diferentes.",
                "📖",
                5,
                species_observed,
            ),
            (
                "naturalista",
                "Naturalista",
                "Descubra 10 espécies diferentes.",
                "🌿",
                10,
                species_observed,
            ),
            (
                "madrugador",
                "Madrugador",
                "Registre uma visita antes das 6h.",
                "🌅",
                1,
                dawn_count,
            ),
            (
                "coruja",
                "Coruja",
                "Registre uma visita após as 20h.",
                "🌙",
                1,
                night_count,
            ),
            (
                "cacador_de_raridades",
                "Caçador de Raridades",
                "Aviste uma espécie rara no alimentador.",
                "💎",
                1,
                rare_count,
            ),
            (
                "observador_de_chuva",
                "Observador de Chuva",
                "Registre uma visita em dia de chuva.",
                "🌧️",
                1,
                rain_count,
            ),
            (
                "dedicado",
                "Dedicado",
                "Acumule 100 visitas registradas.",
                "🏅",
                100,
                total_visits,
            ),
            (
                "constante",
                "Constante",
                "Registre aves em 7 dias diferentes.",
                "📅",
                7,
                active_days,
            ),
        ]

        return [
            {
                "id": badge_id,
                "name": name,
                "description": description,
                "icon": icon,
                "target": target,
                "progress": min(progress, target),
                "unlocked": progress >= target,
            }
            for (badge_id, name, description, icon, target, progress) in definitions
        ]
