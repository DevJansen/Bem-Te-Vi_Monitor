"""Visitantes Silvestres / Convidados Especiais (o "Modo Esquilo").

Expõe o painel dos bichos que **não são aves** e visitam o comedouro — esquilos,
gatos, gambás e companhia. O Alaris Core registra essas aparições à parte: elas
não entram na Life List ("Minhas Aves") nem nas estatísticas ornitológicas, mas
ganham contadores divertidos, prateleira própria na Galeria ("Convidados do
Jardim") e uma medalha secreta no Álbum de Conquistas.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.domain.models import VisitOut, WildlifeSummaryOut
from app.infra.database.analytics_repository import AnalyticsRepository
from app.infra.database.repository import VISITOR_KIND_ESPECIAL, VisitRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wildlife", tags=["wildlife"])


@router.get("/summary", response_model=WildlifeSummaryOut)
def get_wildlife_summary() -> WildlifeSummaryOut:
    """Resumo dos Visitantes Especiais: contagens, grupos e estatísticas lúdicas."""
    try:
        raw = AnalyticsRepository(get_settings().db_path).wildlife_summary()
        return WildlifeSummaryOut(**raw)
    except Exception as exc:
        logger.exception("get_wildlife_summary failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível resumir os Visitantes Especiais.",
        ) from exc


@router.get("/visits", response_model=list[VisitOut])
async def list_wildlife_visits(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    today: bool = Query(
        default=False, description="Restringe aos Visitantes Especiais de hoje."
    ),
) -> list[VisitOut]:
    """Capturas dos Visitantes Especiais (prateleira "Convidados do Jardim")."""
    repo = VisitRepository(get_settings().db_path)
    try:
        if today:
            rows = repo.list_today(limit=limit, visitor_kind=VISITOR_KIND_ESPECIAL)
        else:
            rows = repo.list(
                limit=limit, offset=offset, visitor_kind=VISITOR_KIND_ESPECIAL
            )
        return [VisitRepository.to_out(r) for r in rows]
    except Exception as exc:
        logger.exception("list_wildlife_visits failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível listar os Visitantes Especiais.",
        ) from exc
