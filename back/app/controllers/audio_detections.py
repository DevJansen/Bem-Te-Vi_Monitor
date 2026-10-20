"""Rotas REST das detecções sonoras (Bioacústica / BirdNET).

Além da listagem paginada usada pela aba **Detecção Sonora**, este módulo expõe
o player do clipe gravado (``/{id}/audio``), a associação **manual** à espécie da
Life List (``/{id}/identify``) e as consultas à **IA externa**: identificar a
espécie pelo **espectrograma** do áudio (``/{id}/identify-external``) e buscar a
ficha ornitológica profunda (``/{id}/ask-ai``).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response

from app.core.config import get_settings
from app.core.rate_limiter import limiter
from app.domain.models import (
    AudioAnalysisStatusOut,
    AudioDetectionIdentify,
    AudioDetectionOut,
    AudioDetectionPage,
    AudioInputDevicesOut,
    SpeciesConsultOut,
)
from app.infra.database.audio_repository import AudioDetectionRepository
from app.infra.database.repository import BirdSpeciesRepository, SettingsRepository
from app.services.audio_analysis import get_audio_analysis_service
from app.services.audio_clips import resolve_audio_clip, spectrogram_jpeg_from_wav
from app.services.audio_devices import build_audio_input_devices
from app.services.external_species_identifier import (
    ExternalIdentificationError,
    consult_species_profile,
    identify_spectrogram,
)
from app.services.species_catalog import EspecieNaoAveError, match_or_create_species
from app.services.spectrogram import (
    ensure_detection_spectrogram,
    remove_detection_spectrogram,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/audio-detections", tags=["audio"])

STATUS_IA = "Identificado por IA Externa"
STATUS_MANUAL = "Identificado manualmente"


def _repo() -> AudioDetectionRepository:
    return AudioDetectionRepository(get_settings().db_path)


def _to_out(row: dict) -> AudioDetectionOut:
    """Converte a linha do banco no modelo de saída (com URLs de mídia)."""
    audio_url = (
        f"/api/audio-detections/{row['id']}/audio" if row.get("audio_path") else None
    )
    spectrogram_url = (
        f"/api/audio-detections/{row['id']}/spectrogram"
        if row.get("audio_path")
        else None
    )
    return AudioDetectionOut(
        id=row["id"],
        camera_id=row["camera_id"],
        camera_name=row.get("camera_name") or "",
        detected_at=row["detected_at"],
        species=row["species"],
        scientific_name=row["scientific_name"],
        confidence=float(row["confidence"]),
        linked_visit_id=row.get("linked_visit_id"),
        audio_url=audio_url,
        spectrogram_url=spectrogram_url,
        species_id=row.get("species_id"),
        identification_status=row.get("identification_status"),
        temperature=row.get("temperature"),
        humidity=row.get("humidity"),
        weather_code=row.get("weather_code"),
        wind_speed=row.get("wind_speed"),
        is_nfc=bool(row.get("is_nfc") or 0),
        nfc_score=row.get("nfc_score"),
        night_date=row.get("night_date"),
    )


@router.get("", response_model=list[AudioDetectionOut])
def list_audio_detections(
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[AudioDetectionOut]:
    try:
        rows = _repo().list_recent(limit, offset)
        return [_to_out(row) for row in rows]
    except Exception as exc:
        logger.exception("list_audio_detections failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar as detecções sonoras.",
        ) from exc


@router.get("/page", response_model=AudioDetectionPage)
def page_audio_detections(
    limit: int = Query(default=5, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> AudioDetectionPage:
    """Página de detecções sonoras (paginação fluida da aba dedicada)."""
    try:
        repo = _repo()
        rows = repo.list_recent(limit, offset)
        return AudioDetectionPage(
            items=[_to_out(row) for row in rows],
            total=repo.count(),
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.exception("page_audio_detections failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar as detecções sonoras.",
        ) from exc


@router.get("/nfc", response_model=AudioDetectionPage)
def page_audio_nfc_detections(
    limit: int = Query(default=5, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    night_date: str | None = Query(default=None, description="Noite em vigor (AAAA-MM-DD)."),
) -> AudioDetectionPage:
    """Aba **Viajantes Noturnos (Migração)**: detecções NFC da janela noturna."""
    try:
        repo = _repo()
        rows, total = repo.list_nfc(limit=limit, offset=offset, night_date=night_date)
        return AudioDetectionPage(
            items=[_to_out(row) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        logger.exception("page_audio_nfc_detections failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar os viajantes noturnos.",
        ) from exc


@router.get("/status", response_model=AudioAnalysisStatusOut)
def get_audio_analysis_status() -> AudioAnalysisStatusOut:
    try:
        db_path = get_settings().db_path
        setting = SettingsRepository(db_path).get("audio_analysis_enabled", "false")
        enabled = setting.lower() in {"1", "true", "yes", "on"}
        status = get_audio_analysis_service().get_status(enabled=enabled)
        return AudioAnalysisStatusOut(**status)
    except Exception as exc:
        logger.exception("get_audio_analysis_status failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível consultar o estado da análise sonora.",
        ) from exc


@router.get("/devices", response_model=AudioInputDevicesOut)
def list_audio_input_devices() -> AudioInputDevicesOut:
    """Lista os dispositivos de entrada de áudio disponíveis no sistema."""
    try:
        selected = (
            SettingsRepository(get_settings().db_path).get("audio_input_device", "")
            or ""
        )
        return AudioInputDevicesOut(**build_audio_input_devices(selected))
    except Exception as exc:
        logger.exception("list_audio_input_devices failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível listar os dispositivos de áudio.",
        ) from exc


@router.get("/{detection_id}/audio")
def get_audio_detection_clip(detection_id: str) -> FileResponse:
    """Serve o clipe de áudio gravado da detecção (player da aba dedicada)."""
    row = _repo().get(detection_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Detecção sonora não encontrada.")
    path = resolve_audio_clip(row.get("audio_path"))
    if path is None:
        raise HTTPException(
            status_code=404, detail="O clipe de áudio desta detecção não está disponível."
        )
    return FileResponse(path, media_type="audio/wav", filename=path.name)


@router.get("/{detection_id}/spectrogram")
def get_audio_detection_spectrogram(detection_id: str) -> FileResponse:
    """Serve (ou gera sob demanda) o espectrograma visual do canto gravado."""
    row = _repo().get(detection_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Detecção sonora não encontrada.")
    if not row.get("audio_path"):
        raise HTTPException(
            status_code=404,
            detail="Esta detecção não tem clipe de áudio para gerar o espectrograma.",
        )

    title_parts = [
        str(row.get("species") or "").strip(),
        str(row.get("scientific_name") or "").strip(),
    ]
    title = " · ".join(part for part in title_parts if part) or "Canto identificado"
    path = ensure_detection_spectrogram(
        detection_id,
        row.get("audio_path"),
        title=f"Espectrograma · {title}",
    )
    if path is None:
        raise HTTPException(
            status_code=422,
            detail="Não foi possível gerar o espectrograma desta detecção.",
        )
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@router.put("/{detection_id}/identify", response_model=AudioDetectionOut)
def identify_audio_detection(
    detection_id: str, payload: AudioDetectionIdentify
) -> AudioDetectionOut:
    """Associa **manualmente** a detecção sonora a uma espécie da Life List."""
    repo = _repo()
    row = repo.get(detection_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Detecção sonora não encontrada.")

    common_name = (payload.common_name or "").strip() or None
    scientific_name = (payload.scientific_name or "").strip() or None
    species_id = payload.species_id

    if species_id:
        species = BirdSpeciesRepository(get_settings().db_path).get(species_id)
        if species is None:
            raise HTTPException(status_code=404, detail="Espécie não encontrada.")
        common_name = species.get("common_name") or common_name
        scientific_name = species.get("scientific_name") or scientific_name

    updated = repo.identify(
        detection_id,
        species=common_name,
        scientific_name=scientific_name,
        species_id=species_id,
        status_label=STATUS_MANUAL,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Detecção sonora não encontrada.")
    return _to_out(updated)


@router.post("/{detection_id}/identify-external", response_model=AudioDetectionOut)
@limiter.limit("5/minute")
def identify_audio_external(
    request: Request,
    detection_id: str,
    add_to_catalog: bool = Query(
        default=False,
        description="Cadastra a espécie identificada na Life List e associa a detecção.",
    ),
) -> AudioDetectionOut:
    """Analisa o **espectrograma** da detecção sonora com a IA externa.

    Constrói o espectrograma a partir do clipe de áudio gravado, envia à IA
    (Google Gemini ou compatível) e atualiza a detecção com os nomes retornados.
    """
    repo = _repo()
    row = repo.get(detection_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Detecção sonora não encontrada.")

    clip = resolve_audio_clip(row.get("audio_path"))
    if clip is None:
        raise HTTPException(
            status_code=409,
            detail="Esta detecção não tem clipe de áudio para analisar.",
        )

    spectrogram = spectrogram_jpeg_from_wav(clip)
    if spectrogram is None:
        raise HTTPException(
            status_code=422,
            detail="Não foi possível gerar o espectrograma desta detecção.",
        )

    try:
        identification = identify_spectrogram(spectrogram)
    except ExternalIdentificationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    species_id: str | None = row.get("species_id")
    if add_to_catalog:
        try:
            match = match_or_create_species(
                common_name=identification.common_name,
                scientific_name=identification.scientific_name,
            )
            species_id = str(match.species["id"])
        except EspecieNaoAveError:
            # A IA pode devolver um animal que não é ave; não polui a Life List.
            species_id = None
        except Exception:
            logger.exception(
                "Falha ao cadastrar espécie da detecção sonora detection=%s",
                detection_id,
            )

    updated = repo.identify(
        detection_id,
        species=identification.common_name,
        scientific_name=identification.scientific_name,
        species_id=species_id,
        status_label=STATUS_IA,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Detecção sonora não encontrada.")
    return _to_out(updated)


@router.post("/{detection_id}/ask-ai", response_model=SpeciesConsultOut)
@limiter.limit("5/minute")
def ask_ai_about_audio_detection(
    request: Request,
    detection_id: str,
    refresh: bool = Query(default=False),
) -> SpeciesConsultOut:
    """Ficha ornitológica profunda da espécie detectada por som (IA externa)."""
    repo = _repo()
    row = repo.get(detection_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Detecção sonora não encontrada.")

    if not refresh:
        cached = repo.parse_ai_consult(row.get("ai_consult_json"))
        if cached and cached.get("common_name"):
            return SpeciesConsultOut(**{**cached, "cached": True})

    settings = get_settings()
    if not settings.ai_external_api_key:
        raise HTTPException(
            status_code=503,
            detail="Configure AI_EXTERNAL_API_KEY para habilitar a consulta externa",
        )

    common_name = str(row.get("species") or "").strip()
    scientific_name = str(row.get("scientific_name") or "").strip()
    if not common_name and not scientific_name:
        raise HTTPException(
            status_code=422,
            detail="Identifique a espécie antes de consultar a IA.",
        )

    try:
        consult = consult_species_profile(
            common_name=common_name, scientific_name=scientific_name
        )
    except ExternalIdentificationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload = {
        **consult.as_dict(),
        "provider": consult.provider,
        "model": consult.model,
        "image_source": None,
        "generated_at": None,
        "cached": False,
    }
    repo.set_ai_consult(detection_id, json.dumps(payload, ensure_ascii=False))
    return SpeciesConsultOut(**payload)


@router.delete("/{detection_id}", status_code=204)
def delete_audio_detection(detection_id: str) -> Response:
    """Remove uma detecção sonora do histórico."""
    from app.infra.database.connection import db_session

    with db_session(get_settings().db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM audio_detections WHERE id = ?", (detection_id,)
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404, detail="Detecção sonora não encontrada."
            )
    # Remove também a imagem derivada (o WAV original é preservado para
    # auditoria/retention e pode ser limpo pela tarefa de mídia).
    remove_detection_spectrogram(detection_id)
    return Response(status_code=204)
