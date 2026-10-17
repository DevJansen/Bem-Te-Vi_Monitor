"""Read-only queries used by habit analytics and the life list."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.infra.database.connection import db_session
from app.infra.database.repository import (
    SQL_DATA_LOCAL,
    SQL_HORA_LOCAL,
    SQL_HORA_LOCAL_2D,
    SQL_SO_AVES,
    _media_url,
    _optional_float,
)
from app.domain.avifauna_sul import descrever, info_especie
from app.domain.fauna_taxonomy import grupo_por_chave
from app.core.config import get_settings
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


def _crop_url(visit_id: str | None) -> str | None:
    """URL do recorte tratado da ave (close-up do Alaris Core), se o arquivo existir.

    Os recortes ficam em ``app-data/crops`` (irmã da pasta estática ``captures``)
    e são servidos pelo endpoint dedicado ``/api/visits/{id}/crop``.
    """
    if not visit_id:
        return None
    crop_path = get_settings().crops_dir / f"{visit_id}.jpg"
    return f"/api/visits/{visit_id}/crop" if crop_path.is_file() else None


def _parse_ai_consult(raw: str | None) -> dict[str, Any] | None:
    """Lê o cache da ficha ornitológica da IA externa gravado na espécie."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _visit_image_url(visit_id: str | None, thumbnail_path: str | None) -> str | None:
    """Melhor imagem **tratada** de uma visita, validada em disco.

    Prefere o recorte da ave (close-up já tratado pelo Alaris Core) e, na falta,
    a thumbnail oficial — conferindo que o arquivo realmente existe para nunca
    entregar uma imagem quebrada ao front-end.
    """
    crop = _crop_url(visit_id)
    if crop:
        return crop
    if thumbnail_path:
        normalized = str(thumbnail_path).replace("\\", "/").lstrip("/")
        candidate = get_settings().captures_dir / normalized
        if candidate.is_file():
            return _media_url(thumbnail_path)
    return None


class AnalyticsRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def summary(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        today_prefix = now.date().isoformat()
        week_start = (now - timedelta(days=7)).isoformat()

        with db_session(self.db_path) as conn:
            counts = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total_visits,
                    SUM(CASE WHEN {SQL_DATA_LOCAL} = ? THEN 1 ELSE 0 END) AS visits_today,
                    SUM(CASE WHEN detected_at >= ? THEN 1 ELSE 0 END) AS visits_last_7_days,
                    COALESCE(AVG(dwell_seconds), 0) AS average_duration_seconds
                FROM visits
                WHERE {SQL_SO_AVES}
                """,
                (today_prefix, week_start),
            ).fetchone()
            leader = conn.execute(
                f"""
                SELECT COALESCE(
                    bs.common_name,
                    NULLIF(v.species, 'bird'),
                    'Ave (genérica)'
                ) AS species_name, COUNT(*) AS visit_count
                FROM visits v
                LEFT JOIN bird_species bs ON bs.id = v.species_id
                WHERE {SQL_SO_AVES}
                GROUP BY species_name
                ORDER BY visit_count DESC, species_name COLLATE NOCASE ASC
                LIMIT 1
                """
            ).fetchone()
            peak = conn.execute(
                f"""
                SELECT {SQL_HORA_LOCAL_2D} AS hour, COUNT(*) AS visit_count
                FROM visits
                WHERE {SQL_SO_AVES} AND length(detected_at) >= 13
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
                f"""
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
                WHERE {SQL_SO_AVES}
                """
            ).fetchone()
            condition_rows = conn.execute(
                f"""
                SELECT
                    weather_code AS condition,
                    COUNT(*) AS visits,
                    AVG(temperature) AS avg_temperature,
                    AVG(humidity) AS avg_humidity,
                    AVG(wind_speed) AS avg_wind_speed
                FROM visits
                WHERE {SQL_SO_AVES} AND weather_code IS NOT NULL
                GROUP BY weather_code
                ORDER BY visits DESC, weather_code COLLATE NOCASE ASC
                """
            ).fetchall()
            hour_rows = conn.execute(
                f"""
                SELECT
                    {SQL_HORA_LOCAL_2D} AS hour,
                    COUNT(*) AS visits,
                    AVG(temperature) AS avg_temperature
                FROM visits
                WHERE {SQL_SO_AVES} AND length(detected_at) >= 13
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
                f"""
                SELECT {SQL_HORA_LOCAL_2D} AS hour, COUNT(*) AS visit_count
                FROM visits
                WHERE {SQL_SO_AVES} AND length(detected_at) >= 13
                GROUP BY hour
                """
            ).fetchall()

        counts = {str(row["hour"]): int(row["visit_count"]) for row in rows}
        return [
            {"hour": f"{hour:02d}", "visits": counts.get(f"{hour:02d}", 0)}
            for hour in range(24)
        ]

    def total_visits(self) -> int:
        """Número total de visitas de **aves** (Visitantes Especiais à parte)."""
        with db_session(self.db_path) as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM visits WHERE {SQL_SO_AVES}"
            ).fetchone()
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
                WHERE (v.temperature IS NOT NULL OR v.weather_code IS NOT NULL)
                    AND v.visitor_kind = 'bird'
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
                        SELECT best.id
                        FROM visits AS best
                        WHERE best.species_id = bs.id
                        ORDER BY best.confidence DESC, best.detected_at DESC
                        LIMIT 1
                    ) AS best_visit_id,
                    (
                        SELECT best.thumbnail_path
                        FROM visits AS best
                        WHERE best.species_id = bs.id
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
            # Miniatura do card: prioriza o **recorte tratado** (close-up da ave)
            # do melhor registro, caindo para a thumbnail oficial e, por fim,
            # para a foto de referência. Os arquivos são validados em disco.
            best_photo_url = _visit_image_url(
                row["best_visit_id"], row["best_photo_path"]
            )
            result.append(
                {
                    "id": row["id"],
                    "common_name": row["common_name"],
                    "scientific_name": row["scientific_name"],
                    "description": row["description"] or "",
                    "is_unlocked": row["first_seen_at"] is not None,
                    "first_seen_at": row["first_seen_at"],
                    "featured_photo_url": first_visit_photo or reference_image_url,
                    "reference_image_url": reference_image_url,
                    "sightings_count": sightings,
                    # Campos gamificados do álbum de figurinhas.
                    "visits_count": sightings,
                    "rarity": rarity,
                    "best_photo_url": best_photo_url or reference_image_url,
                    "badges": _species_badges(sightings, rarity),
                    # Status ecológico regional (base do Sul do Brasil / SC).
                    "ecological_status": status_ecologico["status"],
                    "ecological_status_label": status_ecologico["label"],
                    "ecological_badge": status_ecologico["badge"],
                }
            )
        return result

    def species_profile(self, species_id: str) -> dict[str, Any] | None:
        """Ficha técnica completa de uma espécie (Minhas Aves / Álbum).

        Cruza o histórico de avistagens (contagem, primeira/última vez, dias
        ativos e permanência média), o histograma de horários de pico, a
        temperatura/umidade média preferida (Open-Meteo) e o status ecológico
        regional. Devolve ``None`` quando a espécie não existe.
        """
        with db_session(self.db_path) as conn:
            species = conn.execute(
                "SELECT * FROM bird_species WHERE id = ?", (species_id,)
            ).fetchone()
            if species is None:
                return None

            stats = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS visits_count,
                    MIN(detected_at) AS first_seen_at,
                    MAX(detected_at) AS last_seen_at,
                    COUNT(DISTINCT {SQL_DATA_LOCAL}) AS active_days,
                    AVG(dwell_seconds) AS average_dwell_seconds,
                    AVG(temperature) AS avg_temperature,
                    MIN(temperature) AS min_temperature,
                    MAX(temperature) AS max_temperature,
                    AVG(humidity) AS avg_humidity
                FROM visits
                WHERE species_id = ?
                """,
                (species_id,),
            ).fetchone()
            hourly_rows = conn.execute(
                f"""
                SELECT
                    {SQL_HORA_LOCAL_2D} AS hour,
                    COUNT(*) AS visits,
                    AVG(temperature) AS avg_temperature
                FROM visits
                WHERE species_id = ? AND length(detected_at) >= 13
                GROUP BY hour
                """,
                (species_id,),
            ).fetchall()
            weather_rows = conn.execute(
                """
                SELECT
                    weather_code AS condition,
                    COUNT(*) AS visits,
                    AVG(temperature) AS avg_temperature
                FROM visits
                WHERE species_id = ? AND weather_code IS NOT NULL
                GROUP BY weather_code
                ORDER BY visits DESC, weather_code COLLATE NOCASE ASC
                """,
                (species_id,),
            ).fetchall()
            best = conn.execute(
                """
                SELECT id, thumbnail_path
                FROM visits
                WHERE species_id = ?
                ORDER BY confidence DESC, detected_at DESC
                LIMIT 1
                """,
                (species_id,),
            ).fetchone()
            sighting_rows = conn.execute(
                """
                SELECT
                    id, detected_at, confidence, thumbnail_path,
                    temperature, humidity, weather_code, dwell_seconds
                FROM visits
                WHERE species_id = ?
                ORDER BY detected_at DESC, id DESC
                LIMIT 12
                """,
                (species_id,),
            ).fetchall()

        species = dict(species)
        sightings = int(stats["visits_count"] or 0)
        rarity = _rarity_for_sightings(sightings)
        status_ecologico = descrever(
            common_name=species.get("common_name"),
            scientific_name=species.get("scientific_name"),
        )
        info_regional = info_especie(
            common_name=species.get("common_name"),
            scientific_name=species.get("scientific_name"),
        )

        # Histograma das 24 horas (mesmo formato do gráfico do painel).
        counts = {str(row["hour"]): row for row in hourly_rows}
        hourly_distribution: list[dict[str, Any]] = []
        peak_hour: str | None = None
        peak_visits = 0
        for hour in range(24):
            key = f"{hour:02d}"
            row = counts.get(key)
            visits = int(row["visits"]) if row is not None else 0
            hourly_distribution.append(
                {
                    "hour": key,
                    "visits": visits,
                    "avg_temperature": (
                        _optional_float(row["avg_temperature"])
                        if row is not None
                        else None
                    ),
                }
            )
            if visits > peak_visits:
                peak_visits = visits
                peak_hour = f"{key}h"

        reference_path = species.get("reference_image_path")
        reference_image_url = (
            f"/reference-birds/{Path(reference_path).name}"
            if reference_path
            else None
        )

        recent_sightings = [
            {
                "visit_id": row["id"],
                "detected_at": row["detected_at"],
                "confidence": float(row["confidence"]),
                "thumbnail_url": _media_url(row["thumbnail_path"]),
                "crop_url": _crop_url(row["id"]),
                "temperature": _optional_float(row["temperature"]),
                "humidity": _optional_float(row["humidity"]),
                "weather_code": row["weather_code"],
                "dwell_seconds": float(row["dwell_seconds"] or 0.0),
            }
            for row in sighting_rows
        ]

        return {
            "id": species["id"],
            "common_name": species["common_name"],
            "scientific_name": species["scientific_name"],
            "description": species.get("description") or "",
            "reference_image_url": reference_image_url,
            "created_at": species["created_at"],
            "visits_count": sightings,
            "first_seen_at": stats["first_seen_at"],
            "last_seen_at": stats["last_seen_at"],
            "active_days": int(stats["active_days"] or 0),
            "average_dwell_seconds": _optional_float(stats["average_dwell_seconds"]),
            "best_photo_url": (
                _visit_image_url(
                    best["id"] if best is not None else None,
                    best["thumbnail_path"] if best is not None else None,
                )
                or reference_image_url
            ),
            "rarity": rarity,
            "badges": _species_badges(sightings, rarity),
            "ecological_status": status_ecologico["status"],
            "ecological_status_label": status_ecologico["label"],
            "ecological_badge": status_ecologico["badge"],
            "ecological_notes": (
                info_regional.notes if info_regional is not None else None
            ),
            "peak_hour": peak_hour,
            "hourly_distribution": hourly_distribution,
            "avg_temperature": _optional_float(stats["avg_temperature"]),
            "min_temperature": _optional_float(stats["min_temperature"]),
            "max_temperature": _optional_float(stats["max_temperature"]),
            "avg_humidity": _optional_float(stats["avg_humidity"]),
            "weather_distribution": [
                {
                    "condition": row["condition"],
                    "visits": int(row["visits"]),
                    "avg_temperature": _optional_float(row["avg_temperature"]),
                }
                for row in weather_rows
            ],
            "recent_sightings": recent_sightings,
            "ai_consult": _parse_ai_consult(species.get("ai_consult_json")),
        }

    def achievements(self) -> list[dict[str, Any]]:
        """Medalhas/marcos globais conquistados pelo observador.

        Cada conquista devolve o progresso atual e o alvo, permitindo que o
        front-end desenhe a barra de progresso e o estado bloqueado/desbloqueado.
        As medalhas **secretas** (``secret=True``) só revelam nome e descrição
        depois de desbloqueadas — um easter egg para o observador curioso.
        """
        with db_session(self.db_path) as conn:
            totals = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total_visits,
                    COUNT(DISTINCT species_id) AS species_observed,
                    COUNT(DISTINCT {SQL_DATA_LOCAL}) AS active_days
                FROM visits
                WHERE {SQL_SO_AVES}
                """
            ).fetchone()
            dawn_count = conn.execute(
                f"""
                SELECT COUNT(*) AS c FROM visits
                WHERE {SQL_SO_AVES} AND length(detected_at) >= 13
                    AND {SQL_HORA_LOCAL} < 6
                """
            ).fetchone()["c"]
            night_count = conn.execute(
                f"""
                SELECT COUNT(*) AS c FROM visits
                WHERE {SQL_SO_AVES} AND length(detected_at) >= 13
                    AND {SQL_HORA_LOCAL} >= 20
                """
            ).fetchone()["c"]
            rain_count = conn.execute(
                f"""
                SELECT COUNT(*) AS c FROM visits
                WHERE {SQL_SO_AVES} AND (
                    weather_code LIKE '%Chuva%'
                    OR weather_code LIKE '%Chuvisco%'
                    OR weather_code LIKE '%Pancada%'
                    OR weather_code LIKE '%Tempestade%'
                )
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
            # Badge secreta "O Ladrão de Sementes": esquilos no comedouro.
            squirrel_count = conn.execute(
                "SELECT COUNT(*) AS c FROM visits WHERE visitor_group = 'esquilo'"
            ).fetchone()["c"]

        total_visits = int(totals["total_visits"] or 0)
        species_observed = int(totals["species_observed"] or 0)
        active_days = int(totals["active_days"] or 0)
        dawn_count = int(dawn_count or 0)
        night_count = int(night_count or 0)
        rain_count = int(rain_count or 0)
        rare_count = int(rare_count or 0)
        squirrel_count = int(squirrel_count or 0)

        # (id, nome, descrição, ícone, alvo, progresso atual, secreta)
        definitions: list[tuple[str, str, str, str, int, int, bool]] = [
            (
                "primeira_visita",
                "Primeira Visita",
                "Registre a primeira ave no alimentador.",
                "🐣",
                1,
                total_visits,
                False,
            ),
            (
                "explorador",
                "Explorador",
                "Descubra 3 espécies diferentes.",
                "🔭",
                3,
                species_observed,
                False,
            ),
            (
                "colecionador",
                "Colecionador",
                "Descubra 5 espécies diferentes.",
                "📖",
                5,
                species_observed,
                False,
            ),
            (
                "naturalista",
                "Naturalista",
                "Descubra 10 espécies diferentes.",
                "🌿",
                10,
                species_observed,
                False,
            ),
            (
                "madrugador",
                "Madrugador",
                "Registre uma visita antes das 6h.",
                "🌅",
                1,
                dawn_count,
                False,
            ),
            (
                "coruja",
                "Coruja",
                "Registre uma visita após as 20h.",
                "🌙",
                1,
                night_count,
                False,
            ),
            (
                "cacador_de_raridades",
                "Caçador de Raridades",
                "Aviste uma espécie rara no alimentador.",
                "💎",
                1,
                rare_count,
                False,
            ),
            (
                "observador_de_chuva",
                "Observador de Chuva",
                "Registre uma visita em dia de chuva.",
                "🌧️",
                1,
                rain_count,
                False,
            ),
            (
                "dedicado",
                "Dedicado",
                "Acumule 100 visitas registradas.",
                "🏅",
                100,
                total_visits,
                False,
            ),
            (
                "constante",
                "Constante",
                "Registre aves em 7 dias diferentes.",
                "📅",
                7,
                active_days,
                False,
            ),
            # --- Badge secreta: easter egg do "Modo Esquilo" -------------------
            (
                "ladrao_de_sementes",
                "O Ladrão de Sementes",
                "Flagre um esquilo saqueando o comedouro. 🥜",
                "🐿️",
                1,
                squirrel_count,
                True,
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
                "secret": secret,
            }
            for (badge_id, name, description, icon, target, progress, secret) in definitions
        ]

    def wildlife_summary(self) -> dict[str, Any]:
        """Painel dos **Visitantes Silvestres / Convidados Especiais**.

        Resume as aparições de não-aves (esquilos, gatos, gambás…) no jardim:
        total histórico, o que passou hoje, por grupo, e as estatísticas
        divertidas do "Modo Esquilo" (sementes roubadas, badge secreta).
        """
        today_prefix = datetime.now(timezone.utc).date().isoformat()
        with db_session(self.db_path) as conn:
            totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_visits,
                    MIN(detected_at) AS first_visit_at
                FROM visits
                WHERE visitor_kind != 'bird'
                """
            ).fetchone()
            hoje = conn.execute(
                f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(DISTINCT COALESCE(visitor_group, 'visitante')) AS grupos,
                    SUM(CASE WHEN visitor_group = 'esquilo' THEN 1 ELSE 0 END)
                        AS esquilos
                FROM visits
                WHERE visitor_kind != 'bird' AND {SQL_DATA_LOCAL} = ?
                """,
                (today_prefix,),
            ).fetchone()
            group_rows = conn.execute(
                """
                SELECT
                    COALESCE(visitor_group, 'visitante') AS grupo,
                    COUNT(*) AS visits,
                    MAX(detected_at) AS last_seen_at
                FROM visits
                WHERE visitor_kind != 'bird'
                GROUP BY grupo
                ORDER BY visits DESC, grupo ASC
                """
            ).fetchall()

        total_visits = int(totals["total_visits"] or 0)
        grupos: list[dict[str, Any]] = []
        seeds_stolen_total = 0
        for row in group_rows:
            grupo = grupo_por_chave(row["grupo"])
            visits = int(row["visits"])
            consumo = visits * grupo.consumo_por_visita
            seeds_stolen_total += consumo
            grupos.append(
                {
                    "group": grupo.chave,
                    "label": grupo.rotulo,
                    "icon": grupo.icone,
                    "gallery_category": grupo.categoria_galeria,
                    "visits": visits,
                    "last_seen_at": row["last_seen_at"],
                    "estimated_consumption": consumo,
                    "unit": grupo.unidade,
                }
            )

        esquilos_hoje = int(hoje["esquilos"] or 0)
        return {
            "total_visits": total_visits,
            "visits_today": int(hoje["total"] or 0),
            "visitors_today": int(hoje["grupos"] or 0),
            "squirrel_visits_today": esquilos_hoje,
            "seeds_stolen_today": esquilos_hoje
            * grupo_por_chave("esquilo").consumo_por_visita,
            "seeds_stolen_total": seeds_stolen_total,
            "first_visit_at": totals["first_visit_at"],
            "has_visitors": total_visits > 0,
            "squirrel_badge_unlocked": any(
                item["group"] == "esquilo" for item in grupos
            ),
            "groups": grupos,
            "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
        }

    def today_by_garden(self) -> dict[str, Any]:
        """Visitas de hoje consolidadas e segmentadas por jardim (câmera).

        Usado pelo painel para o seletor "Visão Geral (Todos os Jardins)" vs.
        jardim específico e pelos gráficos de horário de pico por jardim.
        Apenas aves (Visitantes Especiais ficam no painel dedicado).
        """
        today_prefix = datetime.now(timezone.utc).date().isoformat()
        with db_session(self.db_path) as conn:
            consolidated_rows = conn.execute(
                f"""
                SELECT species, COUNT(*) AS c
                FROM visits
                WHERE {SQL_SO_AVES} AND {SQL_DATA_LOCAL} = ?
                GROUP BY species
                """,
                (today_prefix,),
            ).fetchall()
            consolidated_hours = conn.execute(
                f"""
                SELECT {SQL_HORA_LOCAL_2D} AS hour, COUNT(*) AS c
                FROM visits
                WHERE {SQL_SO_AVES} AND {SQL_DATA_LOCAL} = ?
                GROUP BY hour
                """,
                (today_prefix,),
            ).fetchall()
            consolidated_total = conn.execute(
                f"SELECT COUNT(*) AS c FROM visits WHERE {SQL_SO_AVES} AND {SQL_DATA_LOCAL} = ?",
                (today_prefix,),
            ).fetchone()["c"]

            gardens_meta = conn.execute(
                "SELECT id, name, location_label FROM cameras ORDER BY name"
            ).fetchall()
            gardens_out: list[dict[str, Any]] = []
            for cam in gardens_meta:
                cam_id = cam["id"]
                species_rows = conn.execute(
                    f"""
                    SELECT species, COUNT(*) AS c
                    FROM visits
                    WHERE {SQL_SO_AVES} AND {SQL_DATA_LOCAL} = ? AND camera_id = ?
                    GROUP BY species
                    """,
                    (today_prefix, cam_id),
                ).fetchall()
                hour_rows = conn.execute(
                    f"""
                    SELECT {SQL_HORA_LOCAL_2D} AS hour, COUNT(*) AS c
                    FROM visits
                    WHERE {SQL_SO_AVES} AND {SQL_DATA_LOCAL} = ? AND camera_id = ?
                    GROUP BY hour
                    """,
                    (today_prefix, cam_id),
                ).fetchall()
                total = conn.execute(
                    f"SELECT COUNT(*) AS c FROM visits WHERE {SQL_SO_AVES} AND {SQL_DATA_LOCAL} = ? AND camera_id = ?",
                    (today_prefix, cam_id),
                ).fetchone()["c"]
                garden_label = cam["location_label"] or cam["name"] or "Jardim sem nome"
                gardens_out.append(
                    {
                        "camera_id": cam_id,
                        "garden": garden_label,
                        "camera_name": cam["name"],
                        "visits": int(total),
                        "species_counts": {r["species"]: int(r["c"]) for r in species_rows},
                        "visits_by_hour": {
                            (r["hour"] or "00"): int(r["c"]) for r in hour_rows if r["hour"]
                        },
                    }
                )

        return {
            "date": today_prefix,
            "consolidated_visits": int(consolidated_total),
            "consolidated_species_counts": {r["species"]: int(r["c"]) for r in consolidated_rows},
            "consolidated_visits_by_hour": {
                (r["hour"] or "00"): int(r["c"]) for r in consolidated_hours if r["hour"]
            },
            "gardens": gardens_out,
        }
