"""Galeria curada: Momentos Raros / Fotos de Postal.

As rotas ficam sob ``/api/gallery`` para não conflitar com ``/api/visits``
(capturas brutas) nem com ``/api/analytics/timelapses``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Response

from app.core.config import get_settings
from app.domain.models import (
    RareMomentListOut,
    RareMomentRefreshOut,
)
from app.services.rare_moments import get_rare_moments_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/gallery", tags=["gallery"])


@router.get("/rare-moments", response_model=RareMomentListOut)
def list_rare_moments(
    days: int | None = Query(
        default=None,
        ge=1,
        le=90,
        description="Janela da curadoria em dias (padrão: RARE_MOMENTS_DAYS).",
    ),
    limit: int = Query(
        default=24,
        ge=6,
        le=60,
        description="Quantidade máxima de fotos na galeria.",
    ),
) -> RareMomentListOut:
    """Curadoria semanal: fotos mais nítidas + espécies raras/incomuns.

    A primeira chamada após a instalação avalia a nitidez das capturas recentes
    sob demanda (rápido, ~2 ms por foto) e guarda o resultado no banco. Depois
    disso a resposta vem do cache local.
    """
    settings = get_settings()
    janela = days if days is not None else settings.rare_moments_days
    try:
        payload = get_rare_moments_service().highlights(days=janela, limit=limit)
        return RareMomentListOut(**payload)
    except Exception as exc:
        logger.exception("list_rare_moments failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível montar a curadoria de Momentos Raros.",
        ) from exc


@router.post("/rare-moments/refresh", response_model=RareMomentRefreshOut)
def refresh_rare_moments(
    limit: int = Query(
        default=120,
        ge=1,
        le=500,
        description="Quantas capturas novas avaliar nesta varredura.",
    ),
) -> RareMomentRefreshOut:
    """Força uma varredura manual de nitidez das capturas ainda não avaliadas."""
    service = get_rare_moments_service()
    try:
        scanned = service.score_pending(limit=limit)
        return RareMomentRefreshOut(
            scanned=scanned,
            pending=service.pending_count(),
        )
    except Exception as exc:
        logger.exception("refresh_rare_moments failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível atualizar a curadoria de Momentos Raros.",
        ) from exc


@router.get("/rare-moments/{visit_id}/postcard")
def download_postcard(visit_id: str) -> Response:
    """Baixa a foto de postal em JPEG, com moldura e marca d'água do Bem-Te-Vi."""
    content = get_rare_moments_service().build_postcard(visit_id)
    if content is None:
        raise HTTPException(
            status_code=404,
            detail="Foto não encontrada para gerar o postal.",
        )
    filename = f"bem-te-vi-postal-{visit_id[:8]}.jpg"
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, max-age=3600",
        },
    )
