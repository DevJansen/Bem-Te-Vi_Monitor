"""Rotas REST do catálogo local de espécies de aves."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status

from app.core.config import get_settings
from app.domain.models import BirdSpeciesOut
from app.infra.database.repository import BirdSpeciesRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/species", tags=["species"])
MAX_REFERENCE_IMAGE_BYTES = 8 * 1024 * 1024


def _repo() -> BirdSpeciesRepository:
    return BirdSpeciesRepository(get_settings().db_path)


@router.get("", response_model=list[BirdSpeciesOut])
def list_species() -> list[BirdSpeciesOut]:
    try:
        return [BirdSpeciesRepository.to_out(row) for row in _repo().list_all()]
    except Exception as exc:
        logger.exception("Failed to list bird species")
        raise HTTPException(
            status_code=500, detail="Não foi possível carregar o catálogo de aves."
        ) from exc


@router.post("", response_model=BirdSpeciesOut, status_code=status.HTTP_201_CREATED)
async def create_species(
    common_name: str = Form(min_length=1, max_length=120),
    scientific_name: str = Form(min_length=1, max_length=160),
    description: str = Form(default="", max_length=4000),
    reference_image: UploadFile | None = File(default=None),
) -> BirdSpeciesOut:
    common_name = common_name.strip()
    scientific_name = scientific_name.strip()
    description = description.strip()
    if not common_name or not scientific_name:
        raise HTTPException(
            status_code=422, detail="Informe o nome popular e o nome científico."
        )

    settings = get_settings()
    settings.ensure_directories()
    species_id = str(uuid.uuid4())
    reference_image_path: Path | None = None
    relative_path: str | None = None
    if reference_image is not None:
        try:
            image_bytes = await reference_image.read(MAX_REFERENCE_IMAGE_BYTES + 1)
        finally:
            await reference_image.close()
        if not image_bytes or len(image_bytes) > MAX_REFERENCE_IMAGE_BYTES:
            raise HTTPException(
                status_code=413,
                detail="A foto de referência deve ter no máximo 8 MB.",
            )
        decoded = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            raise HTTPException(
                status_code=415, detail="O arquivo enviado não é uma imagem válida."
            )
        encoded_ok, encoded = cv2.imencode(
            ".jpg", decoded, [int(cv2.IMWRITE_JPEG_QUALITY), 88]
        )
        if not encoded_ok:
            raise HTTPException(
                status_code=422, detail="Não foi possível processar a foto enviada."
            )
        reference_image_path = settings.reference_birds_dir / f"{species_id}.jpg"
        try:
            reference_image_path.write_bytes(encoded.tobytes())
        except OSError as exc:
            logger.exception("Failed to save reference bird image")
            raise HTTPException(
                status_code=500, detail="Não foi possível salvar a foto de referência."
            ) from exc
        relative_path = f"reference_birds/{species_id}.jpg"

    try:
        row = _repo().create(
            common_name=common_name,
            scientific_name=scientific_name,
            description=description,
            reference_image_path=relative_path,
            species_id=species_id,
        )
        return BirdSpeciesRepository.to_out(row)
    except Exception as exc:
        if reference_image_path is not None:
            reference_image_path.unlink(missing_ok=True)
        logger.exception("Failed to create bird species")
        raise HTTPException(
            status_code=500, detail="Não foi possível cadastrar a espécie."
        ) from exc


@router.delete("/{species_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_species(species_id: str) -> Response:
    repository = _repo()
    existing = repository.get(species_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Espécie não encontrada.")

    image_path: Path | None = None
    stored_path = existing.get("reference_image_path")
    if stored_path:
        expected_relative = f"reference_birds/{species_id}.jpg"
        if stored_path != expected_relative:
            raise HTTPException(
                status_code=500,
                detail="O caminho da foto de referência não é válido.",
            )
        image_path = get_settings().reference_birds_dir / f"{species_id}.jpg"
        try:
            image_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.exception("Failed to remove reference image species=%s", species_id)
            raise HTTPException(
                status_code=500,
                detail="Não foi possível remover a foto de referência.",
            ) from exc

    deleted = repository.delete(species_id)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Espécie não encontrada.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
