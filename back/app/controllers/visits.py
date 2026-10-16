"""REST routes for bird visit events."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.domain.models import VisitOut, VisitSpeciesAssignment
from app.infra.database.repository import VisitRepository
from app.services.anomaly_log import registrar_retorno_especie
from app.services.external_species_identifier import (
    ExternalIdentificationError,
    identify_bird_image_file,
)
from app.services.species_catalog import find_or_create_species

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
    # Log de anomalia: espécie reaparecendo após longo intervalo.
    if payload.species_id:
        nome = row.get("assigned_species_common_name") or row.get("species")
        if nome:
            registrar_retorno_especie(
                species=str(nome),
                scientific_name=row.get("assigned_species_scientific_name"),
                visit_id=visit_id,
                exclude_visit_id=visit_id,
            )
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


@router.get("/today", response_model=list[VisitOut])
async def list_today_visits(
    limit: int = Query(default=50, ge=1, le=200),
) -> list[VisitOut]:
    """Visitas de hoje (mais recentes primeiro), com a miniatura do YOLOv8."""
    try:
        rows = _repo().list_today(limit=limit)
        return [VisitRepository.to_out(r) for r in rows]
    except Exception as exc:
        logger.exception("list_today_visits failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível listar as visitas de hoje.",
        ) from exc


@router.get("/{visit_id}", response_model=VisitOut)
async def get_visit(visit_id: str) -> VisitOut:
    row = _repo().get(visit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Visit not found")
    return VisitRepository.to_out(row)


@router.get("/{visit_id}/crop")
async def get_visit_crop(visit_id: str) -> FileResponse:
    """Serve o recorte ampliado da ave de uma visita.

    O caminho é reconstruído a partir do ``visit_id`` e validado contra a pasta
    de recortes (``app-data/crops``), impedindo qualquer acesso fora dela
    (proteção contra *path traversal*).
    """
    row = _repo().get(visit_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Visita não encontrada.")

    crop_relative: str | None = None
    try:
        metadata = json.loads(row.get("metadata_json") or "{}")
        if isinstance(metadata, dict):
            crop_relative = metadata.get("crop_path")
    except (TypeError, ValueError):
        crop_relative = None

    expected = Path("crops") / f"{visit_id}.jpg"
    if crop_relative != expected.as_posix():
        raise HTTPException(status_code=404, detail="Recorte não disponível.")

    settings = get_settings()
    crop_path = (settings.app_data_dir / expected).resolve()
    if crop_path.parent != settings.crops_dir.resolve() or not crop_path.is_file():
        raise HTTPException(status_code=404, detail="Recorte não disponível.")

    return FileResponse(crop_path, media_type="image/jpeg")


def _resolve_visit_image(row: dict) -> tuple[Path, str] | None:
    """Escolhe a melhor imagem tratada disponível para a identificação externa.

    Prefere o **recorte da ave** (close-up, já passou pelo enhancement) e, na
    falta, a **thumbnail oficial** em alta definição. Os caminhos são validados
    contra as pastas de mídia (proteção contra *path traversal*). Devolve o
    caminho e um rótulo da origem (``recorte`` ou ``thumbnail``).
    """
    settings = get_settings()
    visit_id = row["id"]

    crops_dir = settings.crops_dir.resolve()
    crop_path = (settings.crops_dir / f"{visit_id}.jpg").resolve()
    if crop_path.parent == crops_dir and crop_path.is_file():
        return crop_path, "recorte"

    thumb_relative = row.get("thumbnail_path")
    if thumb_relative:
        candidate = (settings.captures_dir / thumb_relative).resolve()
        thumbs_dir = settings.thumbs_dir.resolve()
        try:
            candidate.relative_to(thumbs_dir)
        except ValueError:
            return None
        if candidate.is_file():
            return candidate, "thumbnail"
    return None


@router.post("/{visit_id}/identify-external", response_model=VisitOut)
def identify_visit_external(
    visit_id: str,
    add_to_catalog: bool = Query(
        default=False,
        description="Cadastra a espécie no Catálogo Local e associa a visita.",
    ),
) -> VisitOut:
    """Identifica a espécie com a IA externa a partir da imagem **tratada**.

    Usa preferencialmente o recorte tratado da ave (ou a thumbnail oficial em
    alta definição) gerados pelo pipeline de gravação. Com ``add_to_catalog``,
    a espécie identificada é cadastrada no Catálogo Local (Life List) e
    associada automaticamente à visita.
    """
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

    resolved = _resolve_visit_image(row)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail="A imagem tratada desta visita não está disponível para identificação",
        )
    image_path, image_source = resolved

    try:
        identification = identify_bird_image_file(image_path)
    except ExternalIdentificationError as exc:
        logger.warning("External identification failed visit=%s: %s", visit_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    species = f"{identification.common_name} ({identification.scientific_name})"

    # Cadastro automático no Catálogo Local / Life List (opcional). A imagem
    # tratada vira a foto de referência da espécie, quando nova.
    catalog_species_id: str | None = None
    if add_to_catalog:
        try:
            species_row = find_or_create_species(
                common_name=identification.common_name,
                scientific_name=identification.scientific_name,
                reference_image_source=image_path,
            )
            catalog_species_id = str(species_row["id"])
        except Exception:
            logger.exception(
                "Falha ao cadastrar a espécie no catálogo visit=%s", visit_id
            )

    updated = repository.update_external_identification(
        visit_id,
        species=species,
        scientific_name=identification.scientific_name,
        common_name=identification.common_name,
        species_id=catalog_species_id,
        image_source=image_source,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Visit not found")
    # Log de anomalia: espécie reaparecendo após longo intervalo.
    registrar_retorno_especie(
        species=identification.common_name,
        scientific_name=identification.scientific_name,
        visit_id=visit_id,
        exclude_visit_id=visit_id,
    )
    return VisitRepository.to_out(updated)
