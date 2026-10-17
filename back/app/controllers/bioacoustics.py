"""REST routes para o Módulo de Bioacústica Global."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.services.bioacoustics import get_bioacoustics_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bioacoustics", tags=["bioacoustics"])


@router.get("/cross/{camera_id}")
def get_cross_reference(
    camera_id: str,
    janela_minutos: int = Query(default=30, ge=1, le=1440),
) -> list[dict[str, Any]]:
    """Cruzamento áudio × visual de uma câmera (quem está no jardim)."""
    try:
        return get_bioacoustics_service().cruzar_deteccoes(camera_id, janela_minutos)
    except Exception as exc:
        logger.exception("get_cross_reference failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível cruzar as detecções.",
        ) from exc


@router.get("/summary/{camera_id}")
def get_bioacoustics_summary(camera_id: str) -> dict[str, Any]:
    """Resumo bioacústico: espécies ouvidas vs. vistas na última 24h."""
    try:
        return get_bioacoustics_service().resumo_bioacustico(camera_id)
    except Exception as exc:
        logger.exception("get_bioacoustics_summary failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível gerar o resumo bioacústico.",
        ) from exc


@router.get("/audio/{camera_id}")
def stream_audio(camera_id: str):
    """Stream de áudio ao vivo da câmera (PCM 16-bit → WAV).

    O player do painel consome este endpoint para ouvir o som ambiente do
    jardim remoto em tempo real.
    """
    servico = get_bioacoustics_service()
    process = servico.abrir_stream_audio(camera_id)
    if process is None or process.stdout is None:
        raise HTTPException(
            status_code=503,
            detail="Áudio ao vivo indisponível para esta câmera.",
        )

    def gerar_chunks():
        try:
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                yield chunk
        finally:
            process.terminate()
            process.wait(timeout=3)

    return StreamingResponse(
        gerar_chunks(),
        media_type="audio/L16;rate=48000;channels=1",
        headers={"Cache-Control": "no-cache"},
    )
