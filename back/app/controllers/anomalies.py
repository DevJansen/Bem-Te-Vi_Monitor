"""Rotas REST do log de anomalias acústico-visuais.

Expõe os eventos raros (ex.: reaparecimento de uma espécie ausente há meses) para
o painel e para uso científico/ conservacionista.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.domain.models import AnomalyOut
from app.infra.database.repository import AnomalyRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])


def _repo() -> AnomalyRepository:
    return AnomalyRepository(get_settings().db_path)


@router.get("", response_model=list[AnomalyOut])
def list_anomalies(
    limit: int = Query(default=50, ge=1, le=500),
    only_pending: bool = Query(
        default=False, description="Somente anomalias ainda não reconhecidas."
    ),
) -> list[AnomalyOut]:
    """Lista as anomalias mais recentes (mais novas primeiro)."""
    try:
        rows = _repo().list_recent(limit, only_pending=only_pending)
        return [AnomalyRepository.to_out(row) for row in rows]
    except Exception as exc:
        logger.exception("list_anomalies failed")
        raise HTTPException(status_code=500, detail="Falha ao listar anomalias") from exc


@router.get("/pending-count")
def pending_count() -> dict[str, int]:
    """Quantidade de anomalias ainda não reconhecidas (badge do painel)."""
    try:
        return {"pending": _repo().count_pending()}
    except Exception as exc:
        logger.exception("pending_count failed")
        raise HTTPException(status_code=500, detail="Falha ao contar anomalias") from exc


@router.post("/{anomaly_id}/acknowledge", response_model=AnomalyOut)
def acknowledge_anomaly(anomaly_id: str) -> AnomalyOut:
    """Marca uma anomalia como reconhecida (some do badge pendente)."""
    row = _repo().acknowledge(anomaly_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Anomalia não encontrada")
    return AnomalyRepository.to_out(row)
