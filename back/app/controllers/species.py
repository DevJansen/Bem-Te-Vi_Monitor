"""Rotas REST do catálogo local de espécies de aves."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status

from app.core.config import get_settings
from app.domain.models import BirdSpeciesOut, SpeciesConsultOut, SpeciesProfileOut
from app.infra.database.analytics_repository import AnalyticsRepository
from app.infra.database.repository import BirdSpeciesRepository
from app.services.external_species_identifier import (
    ExternalIdentificationError,
    consult_species_profile,
)

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


@router.get("/{species_id}/profile", response_model=SpeciesProfileOut)
def get_species_profile(species_id: str) -> SpeciesProfileOut:
    """Ficha técnica completa da espécie (Minhas Aves / Álbum de Conquistas).

    Devolve o histórico de avistagens, os horários de pico, a temperatura média
    preferida (cruzada com a Open-Meteo), as notas científicas e o status
    ecológico regional — o conteúdo rico exibido no card/página da espécie.
    """
    try:
        profile = AnalyticsRepository(get_settings().db_path).species_profile(
            species_id
        )
    except Exception as exc:
        logger.exception("Failed to load species profile species=%s", species_id)
        raise HTTPException(
            status_code=500, detail="Não foi possível carregar a ficha da espécie."
        ) from exc
    if profile is None:
        raise HTTPException(status_code=404, detail="Espécie não encontrada.")
    return SpeciesProfileOut(**profile)


def _parse_ai_consult(raw: str | None) -> dict | None:
    """Lê o cache da ficha ornitológica gravado em ``bird_species``."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@router.post("/{species_id}/ask-ai", response_model=SpeciesConsultOut)
def ask_ai_about_species(
    species_id: str,
    refresh: bool = Query(
        default=False,
        description="Ignora a ficha em cache e consulta a IA externa novamente.",
    ),
) -> SpeciesConsultOut:
    """Consulta ornitológica profunda da **espécie** (Minhas Aves / Álbum).

    Diferente da consulta por visita, esta parte do cadastro da espécie: usa os
    nomes popular/científico e a **foto de referência tratada** (quando existe)
    para montar o *prompt* ornitológico rico. O resultado fica em cache na própria
    espécie; use ``refresh=true`` para forçar uma nova consulta.
    """
    repository = _repo()
    row = repository.get(species_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Espécie não encontrada.")

    # Cache local: evita gastar chamadas de IA repetindo a mesma consulta.
    if not refresh:
        cached = _parse_ai_consult(row.get("ai_consult_json"))
        if cached and cached.get("common_name"):
            return SpeciesConsultOut(**{**cached, "cached": True})

    settings = get_settings()
    if not settings.ai_external_api_key:
        raise HTTPException(
            status_code=503,
            detail="Configure AI_EXTERNAL_API_KEY para habilitar a consulta externa",
        )

    common_name = str(row.get("common_name") or "").strip()
    scientific_name = str(row.get("scientific_name") or "").strip()
    if not common_name and not scientific_name:
        raise HTTPException(
            status_code=422,
            detail="Cadastre o nome popular ou científico antes de consultar a IA.",
        )

    # Envia a foto de referência tratada (close-up do Alaris), se disponível.
    image_bytes: bytes | None = None
    image_source: str | None = None
    reference_path = row.get("reference_image_path")
    if reference_path:
        candidate = settings.reference_birds_dir / Path(str(reference_path)).name
        if candidate.is_file():
            try:
                image_bytes = candidate.read_bytes()
                image_source = "foto de referência"
            except OSError:
                logger.debug(
                    "Foto de referência ilegível para a consulta species=%s",
                    species_id,
                )
                image_bytes = None

    try:
        consult = consult_species_profile(
            common_name=common_name,
            scientific_name=scientific_name,
            image_bytes=image_bytes,
        )
    except ExternalIdentificationError as exc:
        logger.warning("Consulta externa falhou species=%s: %s", species_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload: dict[str, object] = {
        **consult.as_dict(),
        "provider": consult.provider,
        "model": consult.model,
        "image_source": image_source,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "cached": False,
    }
    repository.set_ai_consult(species_id, json.dumps(payload, ensure_ascii=False))
    return SpeciesConsultOut(**payload)


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
