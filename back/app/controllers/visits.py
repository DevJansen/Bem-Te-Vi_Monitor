"""REST routes for bird visit events."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.domain.models import VisitOut, VisitSpeciesAssignment
from app.infra.database.repository import VisitRepository
from app.services.external_species_identifier import (
    ExternalIdentificationError,
    identify_bird_image,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/visits", tags=["visits"])


def _repo() -> VisitRepository:
    return VisitRepository(get_settings().db_path)


@router.put("/{visit_id}/assign-species", response_model=VisitOut)
def assign_visit_species(
    visit_id: str, payload: VisitSpeciesAssignment
) -> VisitOut:
    try:
        row = _repo().assign_species(visit_id, payload.species_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Espécie não encontrada.") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Visita não encontrada.")
    return VisitRepository.to_out(row)


@router.get("", response_model=list[VisitOut])
async def list_visits(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    camera_id: str | None = None,
    species: str | None = None,
) -> list[VisitOut]:
    try:
        rows = _repo().list(
            limit=limit, offset=offset, camera_id=camera_id, species=species
        )
        return [VisitRepository.to_out(r) for r in rows]
    except Exception as exc:
        logger.exception("list_visits failed")
        raise HTTPException(status_code=500, detail="Failed to list visits") from exc


@router.get("/{visit_id}", response_model=VisitOut)
async def get_visit(visit_id: str) -> VisitOut:
    row = _repo().get(visit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Visit not found")
    return VisitRepository.to_out(row)


@router.post("/{visit_id}/identify-external", response_model=VisitOut)
def identify_visit_external(visit_id: str) -> VisitOut:
    repository = _repo()
    row = repository.get(visit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Visit not found")

    visit = VisitRepository.to_out(row)
    if visit.metadata.get("identification_status") == "Identificado por IA Externa":
        return visit

    settings = get_settings()
    if not settings.ai_external_api_key:
        raise HTTPException(
            status_code=503,
            detail="Configure AI_EXTERNAL_API_KEY para habilitar a identificação externa",
        )

    crop_relative_path = visit.metadata.get("crop_path")
    expected_relative_path = Path("crops") / f"{visit_id}.jpg"
    if crop_relative_path != expected_relative_path.as_posix():
        raise HTTPException(
            status_code=404,
            detail="O recorte desta visita não está disponível para identificação",
        )
    crop_path = (settings.app_data_dir / expected_relative_path).resolve()
    if crop_path.parent != settings.crops_dir.resolve() or not crop_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="O recorte desta visita não está disponível para identificação",
        )

    try:
        image_bytes = crop_path.read_bytes()
    except OSError as exc:
        logger.exception("Failed to read bird crop visit=%s", visit_id)
        raise HTTPException(
            status_code=500,
            detail="Não foi possível ler o recorte da visita",
        ) from exc

    try:
        identification = identify_bird_image(image_bytes)
    except ExternalIdentificationError as exc:
        logger.warning("External identification failed visit=%s: %s", visit_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    species = (
        f"{identification.common_name} ({identification.scientific_name})"
    )
    updated = repository.update_external_identification(
        visit_id,
        species=species,
        scientific_name=identification.scientific_name,
        common_name=identification.common_name,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Visit not found")
    return VisitRepository.to_out(updated)
