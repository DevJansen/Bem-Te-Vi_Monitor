"""Persistência das detecções sonoras do BirdNET (Bioacústica).

Além de gravar cada canto identificado, o repositório:

* associa automaticamente a detecção ao card da espécie na *Life List* quando o
  nome (popular ou científico) já está cadastrado — assim a aba "Minhas Aves"
  também enxerga os registros sonoros;
* permite o vínculo **manual** (o observador escolhe a espécie) e o
  enriquecimento pela **IA externa** (ficha ornitológica em cache).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.infra.database.connection import db_session
from app.services.weather_service import current_weather_for_storage

# Seleção padrão com o nome da câmera (o painel exibe "Jardin X · 14:30").
_SELECT = """
    SELECT ad.*, c.name AS camera_name
    FROM audio_detections ad
    JOIN cameras c ON c.id = ad.camera_id
"""


def _normalizar(texto: str | None) -> str:
    return " ".join((texto or "").strip().casefold().split())


class AudioDetectionRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    # ------------------------------------------------------------------ #
    # Escrita
    # ------------------------------------------------------------------ #
    def _match_species_id(self, conn, common_name: str, scientific_name: str) -> str | None:
        """Procura o card da espécie na Life List pelo nome científico/popular."""
        alvo_cientifico = _normalizar(scientific_name)
        alvo_popular = _normalizar(common_name)
        row = conn.execute(
            """
            SELECT id FROM bird_species
            WHERE lower(trim(scientific_name)) = ?
            LIMIT 1
            """,
            (alvo_cientifico,),
        ).fetchone()
        if row is not None:
            return str(row["id"])
        for candidato in conn.execute("SELECT id, common_name FROM bird_species").fetchall():
            if _normalizar(candidato["common_name"]) == alvo_popular:
                return str(candidato["id"])
        return None

    def create_and_link(
        self,
        *,
        camera_id: str,
        detected_at: str,
        species: str,
        scientific_name: str,
        confidence: float,
        audio_path: str | None = None,
    ) -> dict[str, Any]:
        detection_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        # Condições do tempo no momento da detecção sonora (pode ficar nulo se
        # a internet estiver indisponível — não impede o registro).
        weather = current_weather_for_storage()
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
            # Vínculo automático com a Life List, quando a espécie já é conhecida.
            species_id = self._match_species_id(conn, species, scientific_name)
            conn.execute(
                """
                INSERT INTO audio_detections (
                    id, event_type, camera_id, detected_at, species,
                    scientific_name, confidence, linked_visit_id, created_at,
                    temperature, humidity, weather_code, wind_speed,
                    audio_path, species_id
                ) VALUES (?, 'AUDIO_DETECTION', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    weather.get("temperature"),
                    weather.get("humidity"),
                    weather.get("weather_code"),
                    weather.get("wind_speed"),
                    audio_path,
                    species_id,
                ),
            )
            row = conn.execute(
                f"{_SELECT} WHERE ad.id = ?", (detection_id,)
            ).fetchone()
            if row is None:
                raise RuntimeError("A detecção de áudio não foi persistida.")
            return dict(row)

    def identify(
        self,
        detection_id: str,
        *,
        species: str | None = None,
        scientific_name: str | None = None,
        species_id: str | None = None,
        status_label: str = "Identificado",
    ) -> dict[str, Any] | None:
        """Atualiza a identificação da detecção (manual ou por IA externa)."""
        with db_session(self.db_path) as conn:
            existing = conn.execute(
                "SELECT * FROM audio_detections WHERE id = ?", (detection_id,)
            ).fetchone()
            if existing is None:
                return None
            conn.execute(
                """
                UPDATE audio_detections
                   SET species = COALESCE(?, species),
                       scientific_name = COALESCE(?, scientific_name),
                       species_id = COALESCE(?, species_id),
                       identification_status = ?
                 WHERE id = ?
                """,
                (
                    (species or "").strip() or None,
                    (scientific_name or "").strip() or None,
                    species_id,
                    status_label,
                    detection_id,
                ),
            )
            row = conn.execute(f"{_SELECT} WHERE ad.id = ?", (detection_id,)).fetchone()
            return dict(row) if row else None

    def set_ai_consult(self, detection_id: str, payload_json: str) -> None:
        """Guarda a ficha ornitológica da IA externa em cache na detecção."""
        with db_session(self.db_path) as conn:
            conn.execute(
                "UPDATE audio_detections SET ai_consult_json = ? WHERE id = ?",
                (payload_json, detection_id),
            )

    # ------------------------------------------------------------------ #
    # Leitura
    # ------------------------------------------------------------------ #
    def get(self, detection_id: str) -> dict[str, Any] | None:
        with db_session(self.db_path) as conn:
            row = conn.execute(f"{_SELECT} WHERE ad.id = ?", (detection_id,)).fetchone()
            return dict(row) if row else None

    def count(self) -> int:
        with db_session(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM audio_detections").fetchone()
            return int(row["total"]) if row else 0

    def list_recent(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                f"""
                {_SELECT}
                ORDER BY ad.detected_at DESC, ad.created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, max(0, offset)),
            ).fetchall()
            return [dict(row) for row in rows]

    def linked_species_ids(self) -> list[str]:
        """Ids de espécies (Life List) que possuem ao menos uma detecção sonora."""
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT species_id
                FROM audio_detections
                WHERE species_id IS NOT NULL AND species_id != ''
                """
            ).fetchall()
            return [str(row["species_id"]) for row in rows]

    @staticmethod
    def parse_ai_consult(raw: str | None) -> dict[str, Any] | None:
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return data if isinstance(data, dict) else None
