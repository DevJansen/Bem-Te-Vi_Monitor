"""Módulo de Bioacústica Global.

Cruza as detecções sonoras do BirdNET (áudio do stream da câmera) com as
detecções visuais do Alaris Core, produzindo uma visão unificada de "quem
está no jardim" — visto e ouvido. Também expõe o stream de áudio ao vivo
para o player do painel (som ambiente do jardim remoto).
"""

from __future__ import annotations

import logging
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.domain.fauna_taxonomy import descrever_visitante
from app.infra.database.audio_repository import AudioDetectionRepository
from app.infra.database.connection import db_session
from app.infra.database.repository import CameraRepository, VisitRepository
from app.services.stream_resolver import resolver_url_audio

from app.core.ffmpeg import get_ffmpeg_path

logger = logging.getLogger(__name__)

SAMPLE_RATE = 48_000
CHUNK_SECONDS = 3
CHUNK_BYTES = SAMPLE_RATE * 2 * CHUNK_SECONDS
MIN_CONFIDENCE = 0.70
STATUS_POLL_SECONDS = 2.0


def _audio_engine_issue() -> str | None:
    """Verifica se o motor de bioacústica está pronto (ffmpeg + BirdNET)."""
    if get_ffmpeg_path() is None:
        return "FFmpeg não foi encontrado no PATH do sistema."
    import importlib.util

    if importlib.util.find_spec("birdnetlib") is None:
        return "BirdNET não está instalado."
    return None


class BioacousticsService:
    """Serviço de bioacústica: cross-reference áudio × visual + player ao vivo."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.camera_repo = CameraRepository(self.settings.db_path)
        self.audio_repo = AudioDetectionRepository(self.settings.db_path)
        self.visit_repo = VisitRepository(self.settings.db_path)

    # ------------------------------------------------------------------ #
    # Cross-reference áudio × visual
    # ------------------------------------------------------------------ #

    def cruzar_deteccoes(
        self, camera_id: str, janela_minutos: int = 30
    ) -> list[dict[str, Any]]:
        """Cruza detecções sonoras com detecções visuais da mesma câmera.

        Para cada detecção de áudio, busca a visita visual mais próxima no
        tempo e enriquece o resultado com a espécie vista, a foto e a
        confiança combinada.
        """
        agora = datetime.now(timezone.utc)
        inicio = agora - timedelta(minutes=janela_minutos)
        with db_session(self.settings.db_path) as conn:
            rows = conn.execute(
                """
                SELECT ad.id, ad.detected_at, ad.species, ad.scientific_name,
                       ad.confidence, ad.linked_visit_id, ad.camera_id,
                       v.species AS visual_species, v.confidence AS visual_confidence,
                       v.thumbnail_path, v.location_label
                FROM audio_detections ad
                LEFT JOIN visits v ON v.id = ad.linked_visit_id
                WHERE ad.camera_id = ? AND ad.detected_at >= ?
                ORDER BY ad.detected_at DESC
                LIMIT 50
                """,
                (camera_id, inicio.isoformat()),
            ).fetchall()

        resultado: list[dict[str, Any]] = []
        for row in rows:
            especie_audio = row["species"]
            especie_visual = row["visual_species"]
            # Se a espécie vista é diferente da ouvida, registra ambas.
            especies = {especie_audio}
            if especie_visual and especie_visual.lower() not in {"bird", "passaro", "passaro desconhecido"}:
                especies.add(especie_visual)
            confianca_combinada = max(
                row["confidence"] or 0.0, row["visual_confidence"] or 0.0
            )
            resultado.append(
                {
                    "id": row["id"],
                    "detected_at": row["detected_at"],
                    "camera_id": row["camera_id"],
                    "location_label": row["location_label"],
                    "especie_audio": especie_audio,
                    "especie_visual": especie_visual,
                    "especies": sorted(especies),
                    "confianca_audio": row["confidence"],
                    "confianca_visual": row["visual_confidence"],
                    "confianca_combinada": round(confianca_combinada, 4),
                    "linked_visit_id": row["linked_visit_id"],
                    "thumbnail_path": row["thumbnail_path"],
                }
            )
        return resultado

    def resumo_bioacustico(self, camera_id: str) -> dict[str, Any]:
        """Resumo da bioacústica de uma câmera: espécies ouvidas vs. vistas."""
        com_audio = self.cruzar_deteccoes(camera_id, janela_minutos=1440)
        especies_ouvida: set[str] = set()
        especies_vista: set[str] = set()
        for item in com_audio:
            especies_ouvida.add(item["especie_audio"])
            if item["especie_visual"]:
                especies_vista.add(item["especie_visual"])
        return {
            "camera_id": camera_id,
            "total_deteccoes_audio": len(com_audio),
            "especies_ouvida": sorted(especies_ouvida),
            "especies_vista": sorted(especies_vista),
            "especies_confirmadas": sorted(especies_ouvida & especies_vista),
            "especies_so_audio": sorted(especies_ouvida - especies_vista),
        }

    # ------------------------------------------------------------------ #
    # Player de áudio ao vivo
    # ------------------------------------------------------------------ #

    def abrir_stream_audio(self, camera_id: str) -> subprocess.Popen[bytes] | None:
        """Abre um pipe de áudio (PCM 16-bit) do stream da câmera.

        Retorna o processo ffmpeg ou None se a câmera não suportar áudio.
        """
        issue = _audio_engine_issue()
        if issue:
            logger.warning("Bioacústica indisponível: %s", issue)
            return None
        row = self.camera_repo.get(camera_id)
        if row is None or not row["is_active"]:
            return None
        if row["source_type"] == "usb":
            from app.infra.database.repository import SettingsRepository
            from app.services.audio_devices import resolve_audio_input_args

            settings_repo = SettingsRepository(settings.db_path)
            device = settings_repo.get("audio_input_device", "") or None
            input_args = resolve_audio_input_args(device)
        else:
            from app.infra.camera.crypto import decrypt_secret
            from app.infra.camera.streamer import CameraStreamer, StreamConfig

            config = StreamConfig(
                camera_id=row["id"],
                name=row["name"],
                source_type=row["source_type"],
                stream_url=row["stream_url"],
                username=decrypt_secret(row.get("username")),
                password=decrypt_secret(row.get("password_encrypted")),
            )
            target = CameraStreamer(config).resolve_capture_target()
            if isinstance(target, str):
                # YouTube e outros links web: resolve para stream de ÁUDIO direto.
                target = resolver_url_audio(target)
            if not isinstance(target, str):
                return None

            # Argumentos de entrada conforme o protocolo do stream resolvido.
            if target.startswith("rtsp://") or target.startswith("rtsps://"):
                input_args = ["-rtsp_transport", "tcp", "-i", target]
            elif target.startswith("http://") or target.startswith("https://"):
                input_args = [
                    "-headers",
                    "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36\r\nReferer: https://www.youtube.com/\r\n",
                    "-i",
                    target,
                ]
            else:
                input_args = ["-i", target]

        ffmpeg_bin = get_ffmpeg_path() or "ffmpeg"
        command = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-threads",
            "1",
            *input_args,
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-f",
            "mp3",
            "-acodec",
            "libmp3lame",
            "-b:a",
            "128k",
            "pipe:1",
        ]
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )


_servico: BioacousticsService | None = None
_servico_lock = threading.Lock()


def get_bioacoustics_service() -> BioacousticsService:
    """Singleton do serviço de bioacústica."""
    global _servico
    with _servico_lock:
        if _servico is None:
            _servico = BioacousticsService()
        return _servico
