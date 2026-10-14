"""Routes for deleting visit history and associated local media."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.domain.models import ConfirmHistoryReset, HistoryDeletionOut
from app.services.visit_deletion import (
    delete_all_visits,
    delete_visit_media_and_record,
    delete_visits_before,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/events", tags=["events"])


@router.delete("/all", response_model=HistoryDeletionOut)
def clear_all_events(payload: ConfirmHistoryReset) -> HistoryDeletionOut:
    if payload.confirmation != "EXCLUIR TUDO":
        raise HTTPException(
            status_code=400,
            detail="Confirmação inválida para apagar todo o histórico.",
        )
    try:
        return HistoryDeletionOut(**delete_all_visits())
    except Exception as exc:
        logger.exception("Failed to clear event history")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível limpar todo o histórico.",
        ) from exc


@router.delete("", response_model=HistoryDeletionOut)
def clear_old_events(
    older_than_days: int = Query(ge=1, le=36500),
) -> HistoryDeletionOut:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=older_than_days)).isoformat().replace(
        "+00:00", "Z"
    )
    try:
        result = delete_visits_before(cutoff)
        return HistoryDeletionOut(**result)
    except Exception as exc:
        logger.exception("Failed to clear old event history")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível limpar o histórico antigo.",
        ) from exc


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: str) -> Response:
    try:
        removed_files = delete_visit_media_and_record(event_id)
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=500,
            detail="Não foi possível remover a mídia do registro; o evento foi mantido.",
        ) from exc
    except Exception as exc:
        logger.exception("Failed to delete event id=%s", event_id)
        raise HTTPException(
            status_code=500,
            detail="Não foi possível excluir o registro.",
        ) from exc
    if removed_files is None:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
