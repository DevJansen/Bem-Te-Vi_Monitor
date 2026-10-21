"""Rotas REST do Diário de Campo e das exportações para ciência cidadã.

* ``GET /api/journal`` — diário do dia em JSON (usado pela aba dedicada);
* ``GET /api/journal/export/ebird`` — checklist no **eBird Record Format**
  (Cornell Lab of Ornithology), sem cabeçalho;
* ``GET /api/journal/export/csv`` — planilha limpa em pt-BR.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Response

from app.domain.models import FieldJournalOut
from app.services.field_journal import get_field_journal_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("", response_model=FieldJournalOut)
def get_field_journal(
    day: str | None = Query(
        default=None,
        alias="date",
        description="Dia local no formato AAAA-MM-DD (padrão: hoje).",
    ),
    camera_id: str | None = Query(
        default=None, description="Restringe o diário a um jardim/câmera."
    ),
) -> FieldJournalOut:
    """Compila o Diário de Campo do dia com clima, coordenadas e mídias."""
    try:
        payload = get_field_journal_service().build(day, camera_id)
        return FieldJournalOut(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("get_field_journal failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível montar o Diário de Campo.",
        ) from exc


@router.get("/export/ebird")
def export_field_journal_ebird(
    day: str | None = Query(
        default=None,
        alias="date",
        description="Dia local no formato AAAA-MM-DD (padrão: hoje).",
    ),
    camera_id: str | None = Query(default=None),
) -> Response:
    """Baixa o checklist do dia no formato de importação do eBird."""
    try:
        service = get_field_journal_service()
        content = service.export_ebird(day, camera_id)
        reference_day = service.resolve_day(day)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("export_field_journal_ebird failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível exportar o checklist para o eBird.",
        ) from exc

    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="ebird-bem-te-vi-monitor-{reference_day}.csv"'
            )
        },
    )


@router.get("/export/csv")
def export_field_journal_csv(
    day: str | None = Query(
        default=None,
        alias="date",
        description="Dia local no formato AAAA-MM-DD (padrão: hoje).",
    ),
    camera_id: str | None = Query(default=None),
) -> Response:
    """Baixa a planilha limpa do dia (uma linha por espécie e jardim)."""
    try:
        service = get_field_journal_service()
        content = service.export_csv(day, camera_id)
        reference_day = service.resolve_day(day)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("export_field_journal_csv failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível exportar a planilha do dia.",
        ) from exc

    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="diario-campo-bem-te-vi-monitor-{reference_day}.csv"'
            )
        },
    )
