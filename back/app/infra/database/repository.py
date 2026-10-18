"""Data access for cameras, visits and settings."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.domain.models import (
    AnomalyOut,
    BirdSpeciesOut,
    CameraCreate,
    CameraOut,
    CameraUpdate,
    CameraZones,
    SourceType,
    VisitOut,
    ZoneConfig,
)
from app.core.redact import redact_url
from app.domain.fauna_taxonomy import GRUPO_ESQUILO, descrever_visitante
from app.infra.database.connection import db_session
from app.services.weather_service import current_weather_for_storage

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _optional_float(value: Any) -> float | None:
    """Converte um valor de coluna (possivelmente NULL) em float ou None."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Expressões SQL que respeitam o **fuso local da câmera** (migração 8). Usam a
# hora/data local gravada em cada visita e, na ausência dela (câmeras sem fuso
# cadastrado), caem para o horário UTC — preservando o comportamento anterior.
#   SQL_HORA_LOCAL    → hora local como número inteiro (0..23)
#   SQL_HORA_LOCAL_2D → hora local como texto de 2 dígitos ("05")
#   SQL_DATA_LOCAL    → data local no formato ISO (YYYY-MM-DD)
#
# Atenção: o texto de 2 dígitos usa CASE (e não COALESCE(printf(...))), pois
# ``printf('%02d', NULL)`` devolve "00" no SQLite — o que impediria o fallback.
SQL_HORA_LOCAL = "COALESCE(local_hour, CAST(substr(detected_at, 12, 2) AS INTEGER))"
SQL_HORA_LOCAL_2D = (
    "CASE WHEN local_hour IS NULL "
    "THEN substr(detected_at, 12, 2) "
    "ELSE printf('%02d', local_hour) END"
)
SQL_DATA_LOCAL = "COALESCE(local_date, substr(detected_at, 1, 10))"

# Visitantes Silvestres (migração 9). As estatísticas ornitológicas contam
# **apenas aves**; mamíferos e outros bichos aparecem no painel "Convidados do
# Jardim" e nunca poluem a Life List nem os gráficos de aves.
SQL_SO_AVES = "visitor_kind = 'bird'"
# Valor especial aceito pelos filtros de listagem: "todos os não-aves".
VISITOR_KIND_ESPECIAL = "special"


def _clausula_visitante(
    alias: str, visitor_kind: str | None
) -> tuple[str | None, list[Any]]:
    """Traduz o filtro ``visitor_kind`` numa cláusula SQL + parâmetros.

    Aceita ``"bird"``/``"mammal"``/``"other"`` para um grupo exato e
    ``"special"`` para "qualquer Visitante Especial" (tudo que não é ave).
    """
    if not visitor_kind:
        return None, []
    coluna = f"{alias}.visitor_kind" if alias else "visitor_kind"
    if visitor_kind == VISITOR_KIND_ESPECIAL:
        return f"{coluna} != 'bird'", []
    return f"{coluna} = ?", [visitor_kind]


def _media_url(relative: str | None) -> str | None:
    if not relative:
        return None
    normalized = relative.replace("\\", "/").lstrip("/")
    if normalized.startswith("captures/"):
        return f"/{normalized}"
    return f"/captures/{normalized}"


def _clip_url(relative: str | None) -> str | None:
    """URL de streaming do clipe (endpoint dedicado com suporte a Range).

    Os clipes ficam em `captures/clips/`; servimos apenas o nome do arquivo via
    `/api/videos/<arquivo>`, que trata corretamente o player HTML5.
    """
    if not relative:
        return None
    name = Path(relative.replace("\\", "/")).name
    if not name:
        return None
    return f"/api/videos/{name}"


class CameraRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def list_all(self) -> list[dict[str, Any]]:
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM cameras ORDER BY created_at ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    def get(self, camera_id: str) -> dict[str, Any] | None:
        with db_session(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM cameras WHERE id = ?", (camera_id,)
            ).fetchone()
            return dict(row) if row else None

    def create(
        self,
        payload: CameraCreate,
        username_enc: str | None,
        password_enc: str | None,
    ) -> dict[str, Any]:
        now = _utc_now()
        camera_id = str(uuid.uuid4())
        zones_json = CameraZones(zones=payload.zones).model_dump_json()
        location_label = (payload.location_label or "").strip() or None
        timezone_name = (payload.timezone or "").strip() or None
        country = (payload.country or "").strip() or None
        with db_session(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO cameras (
                    id, name, source_type, stream_url, location_label,
                    latitude, longitude, timezone, country,
                    username, password_encrypted, is_active,
                    ai_enabled, audio_enabled,
                    zones_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    camera_id,
                    payload.name,
                    payload.source_type.value,
                    payload.stream_url,
                    location_label,
                    payload.latitude,
                    payload.longitude,
                    timezone_name,
                    country,
                    username_enc,
                    password_enc,
                    1 if payload.enabled else 0,
                    1 if payload.ai_enabled else 0,
                    1 if payload.audio_enabled else 0,
                    zones_json,
                    now,
                    now,
                ),
            )
        created = self.get(camera_id)
        assert created is not None
        return created

    def update(
        self,
        camera_id: str,
        payload: CameraUpdate,
        username_enc: str | None = None,
        password_enc: str | None = None,
        update_credentials: bool = False,
    ) -> dict[str, Any] | None:
        existing = self.get(camera_id)
        if existing is None:
            return None

        name = payload.name if payload.name is not None else existing["name"]
        source_type = (
            payload.source_type.value
            if payload.source_type is not None
            else existing["source_type"]
        )
        stream_url = (
            payload.stream_url.strip() if payload.stream_url is not None else existing["stream_url"]
        )
        location_label = (
            (payload.location_label or "").strip() or None
            if payload.location_label is not None
            else existing.get("location_label")
        )
        # Localização geográfica opcional (câmeras globais/remotas).
        if payload.clear_location:
            latitude = longitude = timezone_name = country = None
        else:
            latitude = (
                payload.latitude
                if payload.latitude is not None
                else existing.get("latitude")
            )
            longitude = (
                payload.longitude
                if payload.longitude is not None
                else existing.get("longitude")
            )
            timezone_name = (
                (payload.timezone or "").strip() or None
                if payload.timezone is not None
                else existing.get("timezone")
            )
            country = (
                (payload.country or "").strip() or None
                if payload.country is not None
                else existing.get("country")
            )
        is_active = (
            (1 if payload.enabled else 0)
            if payload.enabled is not None
            else existing["is_active"]
        )
        ai_enabled = (
            (1 if payload.ai_enabled else 0)
            if payload.ai_enabled is not None
            else existing.get("ai_enabled", 1)
        )
        audio_enabled = (
            (1 if payload.audio_enabled else 0)
            if payload.audio_enabled is not None
            else existing.get("audio_enabled", 0)
        )
        zones_json = (
            CameraZones(zones=payload.zones).model_dump_json()
            if payload.zones is not None
            else existing["zones_json"]
        )

        if payload.clear_credentials:
            username_enc, password_enc = None, None
            update_credentials = True
        elif not update_credentials:
            username_enc = existing["username"]
            password_enc = existing["password_encrypted"]

        with db_session(self.db_path) as conn:
            conn.execute(
                """
                UPDATE cameras SET
                    name = ?, source_type = ?, stream_url = ?, location_label = ?,
                    latitude = ?, longitude = ?, timezone = ?, country = ?,
                    username = ?, password_encrypted = ?, is_active = ?,
                    ai_enabled = ?, audio_enabled = ?,
                    zones_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    name,
                    source_type,
                    stream_url,
                    location_label,
                    latitude,
                    longitude,
                    timezone_name,
                    country,
                    username_enc,
                    password_enc,
                    is_active,
                    ai_enabled,
                    audio_enabled,
                    zones_json,
                    _utc_now(),
                    camera_id,
                ),
            )
        return self.get(camera_id)

    def delete(self, camera_id: str) -> bool:
        with db_session(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
            return cursor.rowcount > 0

    @staticmethod
    def to_out(row: dict[str, Any], status: str = "idle", night_mode: bool = False) -> CameraOut:
        try:
            zones_data = json.loads(row.get("zones_json") or '{"zones":[]}')
            zones = [ZoneConfig.model_validate(z) for z in zones_data.get("zones", [])]
        except Exception:
            logger.exception("Failed to parse zones for camera %s", row.get("id"))
            zones = []
        return CameraOut(
            id=row["id"],
            name=row["name"],
            source_type=SourceType(row["source_type"]),
            stream_url=redact_url(row["stream_url"]),
            location_label=row.get("location_label"),
            latitude=_optional_float(row.get("latitude")),
            longitude=_optional_float(row.get("longitude")),
            timezone=row.get("timezone"),
            country=row.get("country"),
            has_credentials=bool(row.get("username") or row.get("password_encrypted")),
            is_active=bool(row["is_active"]),
            ai_enabled=bool(row.get("ai_enabled", 1)),
            audio_enabled=bool(row.get("audio_enabled", 0)),
            zones=zones,
            status=status,
            night_mode=bool(night_mode),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class VisitRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def create(
        self,
        *,
        camera_id: str,
        species: str,
        confidence: float,
        detected_at: str,
        dwell_seconds: float,
        clip_path: str | None,
        thumbnail_path: str | None,
        bbox: list[float] | None,
        zone_id: str | None,
        metadata: dict[str, Any] | None = None,
        visit_id: str | None = None,
        temperature: float | None = None,
        humidity: float | None = None,
        weather_code: str | None = None,
        wind_speed: float | None = None,
        local_hour: int | None = None,
        local_date: str | None = None,
        visitor_kind: str = "bird",
        visitor_group: str | None = None,
        location_label: str | None = None,
    ) -> dict[str, Any]:
        vid = visit_id or str(uuid.uuid4())
        # Registra as condições do tempo no momento da visita. Quando o chamador
        # não informa nada, consulta o cache local da Open-Meteo (resiliente a
        # falhas de internet: pode gravar nulos sem interromper a visita).
        if all(
            value is None
            for value in (temperature, humidity, weather_code, wind_speed)
        ):
            weather = current_weather_for_storage()
            temperature = weather.get("temperature")
            humidity = weather.get("humidity")
            weather_code = weather.get("weather_code")
            wind_speed = weather.get("wind_speed")
        with db_session(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO visits (
                    id, camera_id, species, confidence, detected_at, dwell_seconds,
                    clip_path, thumbnail_path, bbox_json, zone_id, metadata_json,
                    temperature, humidity, weather_code, wind_speed,
                    local_hour, local_date, visitor_kind, visitor_group, location_label
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vid,
                    camera_id,
                    species,
                    confidence,
                    detected_at,
                    dwell_seconds,
                    clip_path,
                    thumbnail_path,
                    json.dumps(bbox) if bbox is not None else None,
                    zone_id,
                    json.dumps(metadata or {}),
                    temperature,
                    humidity,
                    weather_code,
                    wind_speed,
                    local_hour,
                    local_date,
                    visitor_kind or "bird",
                    visitor_group,
                    location_label,
                ),
            )
        visit = self.get(vid)
        assert visit is not None
        return visit

    def get(self, visit_id: str) -> dict[str, Any] | None:
        with db_session(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT v.*, c.name AS camera_name,
                    bs.common_name AS assigned_species_common_name,
                    bs.scientific_name AS assigned_species_scientific_name
                FROM visits v
                LEFT JOIN cameras c ON c.id = v.camera_id
                LEFT JOIN bird_species bs ON bs.id = v.species_id
                WHERE v.id = ?
                """,
                (visit_id,),
            ).fetchone()
            return dict(row) if row else None

    def delete(self, visit_id: str) -> bool:
        with db_session(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM visits WHERE id = ?", (visit_id,))
            return cursor.rowcount > 0

    def assign_species(
        self, visit_id: str, species_id: str | None
    ) -> dict[str, Any] | None:
        with db_session(self.db_path) as conn:
            species = None
            if species_id is not None:
                species = conn.execute(
                    "SELECT common_name FROM bird_species WHERE id = ?",
                    (species_id,),
                ).fetchone()
                if species is None:
                    raise LookupError("Species not found")
            cursor = conn.execute(
                """
                UPDATE visits
                SET species_id = ?, species = COALESCE(?, species)
                WHERE id = ?
                """,
                (species_id, species["common_name"] if species else None, visit_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get(visit_id)

    def list_before(self, detected_before: str) -> list[dict[str, Any]]:
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM visits
                WHERE detected_at < ?
                ORDER BY detected_at ASC
                """,
                (detected_before,),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_all(self) -> int:
        with db_session(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM visits")
            return cursor.rowcount

    def update_external_identification(
        self,
        visit_id: str,
        *,
        species: str,
        scientific_name: str,
        common_name: str,
        species_id: str | None = None,
        image_source: str | None = None,
    ) -> dict[str, Any] | None:
        # Taxonomia do Alaris Core: decide se o bicho é uma **ave** (fluxo
        # ornitológico normal) ou um **Visitante Especial** (esquilo, gato…).
        # Não-aves nunca entram na Life List e ganham a prateleira da Galeria.
        visitante = descrever_visitante(common_name, scientific_name)
        with db_session(self.db_path) as conn:
            row = conn.execute(
                "SELECT metadata_json FROM visits WHERE id = ?",
                (visit_id,),
            ).fetchone()
            if row is None:
                return None
            metadata = json.loads(row["metadata_json"] or "{}")
            identification: dict[str, Any] = {
                "scientific_name": scientific_name,
                "common_name": common_name,
            }
            # Registra de qual imagem tratada veio a identificação (recorte ou
            # thumbnail oficial), para auditoria.
            if image_source:
                identification["image_source"] = image_source
            metadata["external_identification"] = identification
            metadata["identification_status"] = "Identificado por IA Externa"
            metadata["visitor"] = visitante.as_metadata()
            if visitante.eh_ave:
                # Status ecológico regional (rótulo automático para o painel).
                try:
                    from app.domain.avifauna_sul import descrever

                    metadata["ecological"] = descrever(
                        common_name=common_name, scientific_name=scientific_name
                    )
                except Exception:
                    logger.debug("Falha ao rotular status ecológico", exc_info=True)
                clausula_species = "species_id = COALESCE(?, species_id)"
                params_species: Any = species_id
            else:
                # Visitante Especial: garante que a visita NÃO fica vinculada a
                # nenhuma espécie de ave da Life List.
                metadata["ecological"] = None
                clausula_species = "species_id = ?"
                params_species = None
            conn.execute(
                f"""
                UPDATE visits
                SET species = ?, {clausula_species}, metadata_json = ?,
                    visitor_kind = ?, visitor_group = ?
                WHERE id = ?
                """,
                (
                    species,
                    params_species,
                    json.dumps(metadata, ensure_ascii=False),
                    visitante.kind.value,
                    visitante.grupo.chave if visitante.grupo else None,
                    visit_id,
                ),
            )
        return self.get(visit_id)

    def update_metadata(
        self, visit_id: str, updates: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Funde (merge raso) chaves no ``metadata_json`` da visita.

        Usado para cachear a ficha ornitológica da IA externa sem sobrescrever
        os demais metadados gravados pelo Alaris Core. Devolve a visita
        atualizada ou ``None`` quando o ``visit_id`` não existe.
        """
        with db_session(self.db_path) as conn:
            row = conn.execute(
                "SELECT metadata_json FROM visits WHERE id = ?", (visit_id,)
            ).fetchone()
            if row is None:
                return None
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except (TypeError, ValueError):
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            metadata.update(updates)
            conn.execute(
                "UPDATE visits SET metadata_json = ? WHERE id = ?",
                (json.dumps(metadata, ensure_ascii=False), visit_id),
            )
        return self.get(visit_id)

    def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        camera_id: str | None = None,
        species: str | None = None,
        visitor_kind: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if camera_id:
            clauses.append("v.camera_id = ?")
            params.append(camera_id)
        if species:
            clauses.append("v.species = ?")
            params.append(species)
        clausula_visitante, params_visitante = _clausula_visitante("v", visitor_kind)
        if clausula_visitante:
            clauses.append(clausula_visitante)
            params.extend(params_visitante)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([limit, offset])
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT v.*, c.name AS camera_name,
                    bs.common_name AS assigned_species_common_name,
                    bs.scientific_name AS assigned_species_scientific_name
                FROM visits v
                LEFT JOIN cameras c ON c.id = v.camera_id
                LEFT JOIN bird_species bs ON bs.id = v.species_id
                {where}
                ORDER BY v.detected_at DESC
                LIMIT ? OFFSET ?
                """,
                params,
            ).fetchall()
            return [dict(r) for r in rows]

    def list_today(
        self, *, limit: int = 100, visitor_kind: str | None = None,
        camera_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Visitas registradas hoje (data UTC do servidor), mais recentes primeiro.

        ``visitor_kind`` permite separar o painel de aves do painel de
        **Visitantes Especiais**: ``"bird"`` só aves, ``"special"`` só não-aves.
        ``camera_id`` restringe a um jardim específico (segmentação por jardim).
        """
        today_prefix = datetime.now(timezone.utc).date().isoformat()
        clausula_visitante, params_visitante = _clausula_visitante("v", visitor_kind)
        clauses = ["v.detected_at LIKE ?"]
        params: list[Any] = [f"{today_prefix}%"]
        if clausula_visitante:
            clauses.append(clausula_visitante)
            params.extend(params_visitante)
        if camera_id:
            clauses.append("v.camera_id = ?")
            params.append(camera_id)
        where = " AND ".join(clauses)
        params.append(limit)
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                f"""
                SELECT v.*, c.name AS camera_name,
                    bs.common_name AS assigned_species_common_name,
                    bs.scientific_name AS assigned_species_scientific_name
                FROM visits v
                LEFT JOIN cameras c ON c.id = v.camera_id
                LEFT JOIN bird_species bs ON bs.id = v.species_id
                WHERE {where}
                ORDER BY v.detected_at DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            return [dict(r) for r in rows]

    def list_clip_paths_between(
        self, start_utc: str, end_utc: str
    ) -> list[str]:
        """Caminhos dos clipes com visita no intervalo UTC ``[start, end)``.

        Usado pela geração do time-lapse diário: só entram visitas que têm clipe
        de vídeo associado. As datas são comparadas como texto no formato
        ``YYYY-MM-DDTHH:MM:SSZ`` (mesmo padrão gravado pelo pipeline).
        """
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT clip_path FROM visits
                WHERE detected_at >= ? AND detected_at < ?
                    AND clip_path IS NOT NULL
                ORDER BY detected_at ASC
                """,
                (start_utc, end_utc),
            ).fetchall()
        return [row["clip_path"] for row in rows if row["clip_path"]]

    def count(self, *, camera_id: str | None = None) -> int:
        with db_session(self.db_path) as conn:
            if camera_id:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM visits WHERE camera_id = ?",
                    (camera_id,),
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) AS c FROM visits").fetchone()
            return int(row["c"]) if row else 0

    def stats(self, camera_id: str | None = None) -> dict[str, Any]:
        """Estatísticas do painel ornitológico + contadores dos Visitantes.

        As métricas de aves ignoram os Visitantes Especiais (mamíferos/outros);
        eles ganham contadores próprios (``visitors_today``, ``squirrel_*`` e a
        estatística divertida ``seeds_stolen_today``).
        """
        today_prefix = datetime.now(timezone.utc).date().isoformat()
        # Filtro opcional por jardim (câmera).
        filtro_cam = " AND camera_id = ?" if camera_id else ""
        params_cam = (camera_id,) if camera_id else ()
        with db_session(self.db_path) as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS c FROM visits WHERE {SQL_SO_AVES}{filtro_cam}",
                params_cam,
            ).fetchone()["c"]
            today = conn.execute(
                f"SELECT COUNT(*) AS c FROM visits "
                f"WHERE {SQL_SO_AVES} AND {SQL_DATA_LOCAL} = ?{filtro_cam}",
                (today_prefix, *params_cam),
            ).fetchone()["c"]
            species_rows = conn.execute(
                f"""
                SELECT species, COUNT(*) AS c
                FROM visits
                WHERE {SQL_SO_AVES}{filtro_cam}
                GROUP BY species
                ORDER BY c DESC
                LIMIT 50
                """,
                params_cam,
            ).fetchall()
            hour_rows = conn.execute(
                f"""
                SELECT {SQL_HORA_LOCAL_2D} AS hour, COUNT(*) AS c
                FROM visits
                WHERE {SQL_SO_AVES} AND {SQL_DATA_LOCAL} = ?{filtro_cam}
                GROUP BY hour
                ORDER BY hour
                """,
                (today_prefix, *params_cam),
            ).fetchall()
            last = conn.execute(
                f"SELECT detected_at FROM visits WHERE {SQL_SO_AVES}{filtro_cam} "
                "ORDER BY detected_at DESC LIMIT 1",
                params_cam,
            ).fetchone()
            # --- Visitantes Silvestres / Convidados Especiais (Modo Esquilo) ---
            visitantes_today = conn.execute(
                f"""
                SELECT COUNT(*) AS total,
                    COUNT(DISTINCT COALESCE(visitor_group, 'visitante')) AS grupos,
                    SUM(CASE WHEN visitor_group = 'esquilo' THEN 1 ELSE 0 END)
                        AS esquilos
                FROM visits
                WHERE visitor_kind != 'bird' AND {SQL_DATA_LOCAL} = ?{filtro_cam}
                """,
                (today_prefix, *params_cam),
            ).fetchone()
            cam_total = conn.execute("SELECT COUNT(*) AS c FROM cameras").fetchone()["c"]
            cam_active = conn.execute(
                "SELECT COUNT(*) AS c FROM cameras WHERE is_active = 1"
            ).fetchone()["c"]

        esquilos_hoje = int(visitantes_today["esquilos"] or 0)
        return {
            "total_visits": int(total),
            "visits_today": int(today),
            "active_cameras": int(cam_active),
            "total_cameras": int(cam_total),
            "species_counts": {r["species"]: int(r["c"]) for r in species_rows},
            "visits_by_hour": {
                (r["hour"] or "00"): int(r["c"]) for r in hour_rows if r["hour"]
            },
            "last_visit_at": last["detected_at"] if last else None,
            "visitors_today": int(visitantes_today["grupos"] or 0),
            "squirrel_visits_today": esquilos_hoje,
            "seeds_stolen_today": esquilos_hoje * GRUPO_ESQUILO.consumo_por_visita,
        }

    @staticmethod
    def to_out(row: dict[str, Any]) -> VisitOut:
        bbox = None
        metadata: dict[str, Any] = {}
        try:
            if row.get("bbox_json"):
                bbox = json.loads(row["bbox_json"])
        except Exception:
            bbox = None
        try:
            metadata = json.loads(row.get("metadata_json") or "{}")
        except Exception:
            metadata = {}

        clip_path = row.get("clip_path")
        thumb_path = row.get("thumbnail_path")
        return VisitOut(
            id=row["id"],
            camera_id=row["camera_id"],
            camera_name=row.get("camera_name"),
            species=row["species"],
            confidence=float(row["confidence"]),
            detected_at=row["detected_at"],
            dwell_seconds=float(row["dwell_seconds"]),
            clip_path=clip_path,
            thumbnail_path=thumb_path,
            clip_url=_clip_url(clip_path),
            thumbnail_url=_media_url(thumb_path),
            bbox=bbox,
            zone_id=row.get("zone_id"),
            species_id=row.get("species_id"),
            assigned_species_common_name=row.get("assigned_species_common_name"),
            assigned_species_scientific_name=row.get(
                "assigned_species_scientific_name"
            ),
            visitor_kind=row.get("visitor_kind") or "bird",
            visitor_group=row.get("visitor_group"),
            location_label=row.get("location_label"),
            temperature=_optional_float(row.get("temperature")),
            humidity=_optional_float(row.get("humidity")),
            weather_code=row.get("weather_code"),
            wind_speed=_optional_float(row.get("wind_speed")),
            metadata=metadata,
        )


class BirdSpeciesRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def list_all(self) -> list[dict[str, Any]]:
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM bird_species ORDER BY common_name COLLATE NOCASE ASC"
            ).fetchall()
            return [dict(row) for row in rows]

    def get(self, species_id: str) -> dict[str, Any] | None:
        with db_session(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM bird_species WHERE id = ?", (species_id,)
            ).fetchone()
            return dict(row) if row else None

    def create(
        self,
        *,
        common_name: str,
        scientific_name: str,
        description: str,
        reference_image_path: str | None,
        species_id: str | None = None,
        ecological_status: str | None = None,
    ) -> dict[str, Any]:
        species_id = species_id or str(uuid.uuid4())
        created_at = _utc_now()
        with db_session(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO bird_species (
                    id, common_name, scientific_name, description,
                    reference_image_path, created_at, ecological_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    species_id,
                    common_name,
                    scientific_name,
                    description,
                    reference_image_path,
                    created_at,
                    ecological_status,
                ),
            )
        species = self.get(species_id)
        assert species is not None
        return species

    def set_ecological_status(
        self, species_id: str, status: str | None
    ) -> dict[str, Any] | None:
        """Atualiza o status ecológico regional de uma espécie."""
        with db_session(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE bird_species SET ecological_status = ? WHERE id = ?",
                (status, species_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get(species_id)

    def set_reference_image(
        self, species_id: str, reference_image_path: str | None
    ) -> dict[str, Any] | None:
        """Define/atualiza a foto de referência (arquivo tratado pelo Alaris)."""
        with db_session(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE bird_species SET reference_image_path = ? WHERE id = ?",
                (reference_image_path, species_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get(species_id)

    def set_ai_consult(
        self, species_id: str, payload_json: str | None
    ) -> dict[str, Any] | None:
        """Grava (ou limpa) o cache da ficha ornitológica da IA externa."""
        with db_session(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE bird_species SET ai_consult_json = ? WHERE id = ?",
                (payload_json, species_id),
            )
            if cursor.rowcount == 0:
                return None
        return self.get(species_id)

    def delete(self, species_id: str) -> dict[str, Any] | None:
        with db_session(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM bird_species WHERE id = ?", (species_id,)
            ).fetchone()
            if row is None:
                return None
            species = dict(row)
            conn.execute("DELETE FROM bird_species WHERE id = ?", (species_id,))
            return species

    @staticmethod
    def to_out(row: dict[str, Any]) -> BirdSpeciesOut:
        from app.domain.avifauna_sul import classificar_status, descrever

        image_path = row.get("reference_image_path")
        image_url = (
            f"/reference-birds/{Path(image_path).name}" if image_path else None
        )
        # O status vem do banco quando já rotulado; senão, é inferido pela base
        # regional (assim espécies antigas ganham o selo sem reprocessamento).
        status_armazenado = row.get("ecological_status")
        if not status_armazenado:
            status_armazenado = classificar_status(
                common_name=row.get("common_name"),
                scientific_name=row.get("scientific_name"),
            ).value
        descricao_status = descrever(
            common_name=row.get("common_name"),
            scientific_name=row.get("scientific_name"),
        )
        return BirdSpeciesOut(
            id=row["id"],
            common_name=row["common_name"],
            scientific_name=row["scientific_name"],
            description=row.get("description") or "",
            reference_image_path=image_path,
            reference_image_url=image_url,
            created_at=row["created_at"],
            ecological_status=status_armazenado,
            ecological_status_label=descricao_status["label"],
            ecological_badge=descricao_status["badge"],
        )


class AnomalyRepository:
    """Armazena e consulta anomalias acústico-visuais (log para biólogos)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def create(
        self,
        *,
        kind: str,
        species: str,
        scientific_name: str | None,
        days_absent: int | None,
        message: str,
        visit_id: str | None,
        details: dict[str, Any] | None = None,
        anomaly_id: str | None = None,
    ) -> dict[str, Any]:
        anomaly_id = anomaly_id or str(uuid.uuid4())
        created_at = _utc_now()
        with db_session(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO anomaly_events (
                    id, kind, created_at, species, scientific_name,
                    days_absent, message, visit_id, acknowledged, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    anomaly_id,
                    kind,
                    created_at,
                    species,
                    scientific_name,
                    days_absent,
                    message,
                    visit_id,
                    json.dumps(details or {}, ensure_ascii=False),
                ),
            )
        return self.get(anomaly_id) or {}

    def get(self, anomaly_id: str) -> dict[str, Any] | None:
        with db_session(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM anomaly_events WHERE id = ?", (anomaly_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_recent(self, limit: int = 50, *, only_pending: bool = False) -> list[dict[str, Any]]:
        with db_session(self.db_path) as conn:
            sql = "SELECT * FROM anomaly_events"
            if only_pending:
                sql += " WHERE acknowledged = 0"
            sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
            rows = conn.execute(sql, (int(limit),)).fetchall()
            return [dict(row) for row in rows]

    def count_pending(self) -> int:
        with db_session(self.db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM anomaly_events WHERE acknowledged = 0"
            ).fetchone()
            return int(row["total"]) if row else 0

    def has_recent_for_species(self, species: str, since_iso: str) -> bool:
        """Indica se já há anomalia recente para a espécie (evita spam)."""
        with db_session(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT 1 FROM anomaly_events
                WHERE species = ? COLLATE NOCASE AND created_at >= ?
                LIMIT 1
                """,
                (species, since_iso),
            ).fetchone()
            return row is not None

    def acknowledge(self, anomaly_id: str) -> dict[str, Any] | None:
        with db_session(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE anomaly_events SET acknowledged = 1 WHERE id = ?",
                (anomaly_id,),
            )
            if cursor.rowcount == 0:
                return None
        return self.get(anomaly_id)

    @staticmethod
    def to_out(row: dict[str, Any]) -> AnomalyOut:
        try:
            details = json.loads(row.get("details_json") or "{}")
        except Exception:
            details = {}
        return AnomalyOut(
            id=row["id"],
            kind=row.get("kind") or "species_return",
            created_at=row["created_at"],
            species=row["species"],
            scientific_name=row.get("scientific_name"),
            days_absent=row.get("days_absent"),
            message=row.get("message") or "",
            visit_id=row.get("visit_id"),
            acknowledged=bool(row.get("acknowledged")),
            details=details,
        )


class SettingsRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def get(self, key: str, default: str | None = None) -> str | None:
        with db_session(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
            if row is None:
                return default
            return str(row["value"])

    def get_json(self, key: str, default: Any = None) -> Any:
        raw = self.get(key)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    def set(self, key: str, value: str) -> None:
        with db_session(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value, _utc_now()),
            )

    def set_json(self, key: str, value: Any) -> None:
        self.set(key, json.dumps(value))

    def get_all(self) -> dict[str, str]:
        with db_session(self.db_path) as conn:
            rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
            return {r["key"]: r["value"] for r in rows}
