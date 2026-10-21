"""REST routes for camera management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from app.core.rate_limiter import limiter

from app.core.config import get_settings
from app.core.redact import extrair_credenciais_da_url
from app.domain.models import (
    CameraAiToggle,
    CameraBioacousticsToggle,
    CameraCreate,
    CameraOut,
    CameraUpdate,
    CameraWeatherOut,
    CameraZones,
)
from app.infra.ai.pipeline import get_pipeline_supervisor
from app.infra.camera.crypto import encrypt_secret
from app.infra.camera.manager import get_camera_manager
from app.infra.database.repository import CameraRepository
from app.services.camera_weather import get_camera_weather_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cameras", tags=["cameras"])


def _repo() -> CameraRepository:
    return CameraRepository(get_settings().db_path)


@router.get("", response_model=list[CameraOut])
async def list_cameras() -> list[CameraOut]:
    try:
        manager = get_camera_manager()
        rows = _repo().list_all()
        return [
            CameraRepository.to_out(
                row,
                status=manager.get_status(row["id"]),
                night_mode=manager.get_night_mode(row["id"]),
            )
            for row in rows
        ]
    except Exception as exc:
        logger.exception("list_cameras failed")
        raise HTTPException(status_code=500, detail="Failed to list cameras") from exc


@router.get("/{camera_id}", response_model=CameraOut)
async def get_camera(camera_id: str) -> CameraOut:
    row = _repo().get(camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return CameraRepository.to_out(
        row,
        status=get_camera_manager().get_status(camera_id),
        night_mode=get_camera_manager().get_night_mode(camera_id),
    )


@router.get("/{camera_id}/weather", response_model=CameraWeatherOut)
async def get_camera_weather(camera_id: str) -> CameraWeatherOut:
    """Clima e horário **locais** do jardim onde a câmera está instalada.

    Requer coordenadas cadastradas (ver a seção de localização do cadastro).
    Sem coordenadas — ou sem internet — devolve ``available=False`` em vez de
    erro, para o painel apenas ocultar o widget sem quebrar a interface.
    """
    row = _repo().get(camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    latitude = row.get("latitude")
    longitude = row.get("longitude")
    if latitude is None or longitude is None:
        return CameraWeatherOut(available=False)

    snapshot = get_camera_weather_service().current_for(
        float(latitude),
        float(longitude),
        timezone_name=row.get("timezone"),
    )
    if snapshot is None:
        return CameraWeatherOut(
            available=False,
            latitude=float(latitude),
            longitude=float(longitude),
            timezone=row.get("timezone"),
        )

    return CameraWeatherOut(
        available=snapshot.available,
        latitude=float(latitude),
        longitude=float(longitude),
        timezone=snapshot.timezone or row.get("timezone"),
        utc_offset_seconds=snapshot.utc_offset_seconds,
        local_time=snapshot.local_time,
        local_time_label=snapshot.local_time_label,
        temperature=snapshot.temperature,
        humidity=snapshot.humidity,
        wind_speed=snapshot.wind_speed,
        condition=snapshot.condition,
        category=snapshot.category,
        icon=snapshot.icon,
        weather_code=snapshot.code,
        is_day=snapshot.is_day,
        fetched_at=snapshot.fetched_at,
        source=snapshot.source,
    )


@router.get("/{camera_id}/zones", response_model=CameraZones)
async def get_camera_zones(camera_id: str) -> CameraZones:
    row = _repo().get(camera_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Camera not found")
    return CameraZones.model_validate_json(
        row.get("zones_json") or '{"zones":[]}'
    )


@router.put("/{camera_id}/zones", response_model=CameraZones)
async def save_camera_zones(camera_id: str, payload: CameraZones) -> CameraZones:
    try:
        repository = _repo()
        if repository.get(camera_id) is None:
            raise HTTPException(status_code=404, detail="Camera not found")
        updated = repository.update(camera_id, CameraUpdate(zones=payload.zones))
        if updated is None:
            raise HTTPException(status_code=404, detail="Camera not found")
        get_pipeline_supervisor().restart_camera(camera_id)
        return CameraZones.model_validate_json(
            updated.get("zones_json") or '{"zones":[]}'
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("save_camera_zones failed for camera %s", camera_id)
        raise HTTPException(status_code=500, detail="Failed to save camera zones") from exc


@router.post("", response_model=CameraOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_camera(request: Request, payload: CameraCreate) -> CameraOut:
    try:
        # Smart Stream Resolver (entrada): o usuário pode simplesmente colar o
        # link. Se ele já trouxer usuário/senha embutidos, separamos da URL para
        # criptografar em repouso; se for público/aberto, segue sem credenciais.
        # Validação SSRF: bloqueia URLs que apontem para recursos internos.
        try:
            from app.services.url_validator import UrlInvalidaError, validar_url_stream

            validar_url_stream(payload.stream_url)
        except UrlInvalidaError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        url_limpa, usuario_url, senha_url = extrair_credenciais_da_url(payload.stream_url)
        if url_limpa != payload.stream_url:
            payload = payload.model_copy(update={"stream_url": url_limpa})
        username = payload.username or usuario_url
        password = payload.password or senha_url

        row = _repo().create(
            payload,
            username_enc=encrypt_secret(username),
            password_enc=encrypt_secret(password),
        )
        if row["is_active"]:
            get_pipeline_supervisor().start_camera(row["id"])
        return CameraRepository.to_out(
            row, status=get_camera_manager().get_status(row["id"])
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("create_camera failed")
        raise HTTPException(status_code=500, detail="Failed to create camera") from exc


@router.put("/{camera_id}", response_model=CameraOut)
async def update_camera(camera_id: str, payload: CameraUpdate) -> CameraOut:
    try:
        # Smart Stream Resolver (entrada): extrai credenciais embutidas no novo
        # link (quando houver), tratando-as como fornecidas explicitamente.
        if payload.stream_url:
            url_limpa, usuario_url, senha_url = extrair_credenciais_da_url(
                payload.stream_url
            )
            if url_limpa != payload.stream_url:
                payload = payload.model_copy(update={"stream_url": url_limpa})
            if payload.username is None and usuario_url is not None:
                payload = payload.model_copy(update={"username": usuario_url})
            if payload.password is None and senha_url is not None:
                payload = payload.model_copy(update={"password": senha_url})

        update_creds = (
            payload.username is not None
            or payload.password is not None
            or payload.clear_credentials
        )
        username_enc = encrypt_secret(payload.username) if payload.username is not None else None
        password_enc = encrypt_secret(payload.password) if payload.password is not None else None
        # If only one credential field sent, keep the other unless clearing
        if update_creds and not payload.clear_credentials:
            existing = _repo().get(camera_id)
            if existing is None:
                raise HTTPException(status_code=404, detail="Camera not found")
            if payload.username is None:
                username_enc = existing.get("username")
            if payload.password is None:
                password_enc = existing.get("password_encrypted")

        row = _repo().update(
            camera_id,
            payload,
            username_enc=username_enc,
            password_enc=password_enc,
            update_credentials=update_creds,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Camera not found")

        connection_changed = (
            payload.stream_url is not None
            or payload.source_type is not None
            or update_creds
            or payload.zones is not None
        )

        if payload.ai_enabled is not None:
            get_pipeline_supervisor().set_camera_ai_enabled(camera_id, payload.ai_enabled)

        if payload.audio_enabled is not None:
            from app.services.audio_analysis import get_audio_analysis_service

            get_audio_analysis_service().trigger_reconcile()

        if payload.enabled is not None:
            if payload.enabled:
                get_pipeline_supervisor().start_camera(camera_id)
            else:
                get_pipeline_supervisor().stop_camera(camera_id)
        elif connection_changed:
            get_pipeline_supervisor().restart_camera(camera_id)

        return CameraRepository.to_out(
            row,
            status=get_camera_manager().get_status(camera_id),
            night_mode=get_camera_manager().get_night_mode(camera_id),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("update_camera failed")
        raise HTTPException(status_code=500, detail="Failed to update camera") from exc


@router.patch("/{camera_id}/ai", response_model=CameraOut)
async def toggle_camera_ai(camera_id: str, payload: CameraAiToggle) -> CameraOut:
    """Ativa ou pausa o Bem-Te-Vi Core (YOLOv8 + gravação) para a câmera em tempo real."""
    repo = _repo()
    existing = repo.get(camera_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    row = repo.update(camera_id, CameraUpdate(ai_enabled=payload.enabled))
    if row is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    get_pipeline_supervisor().set_camera_ai_enabled(camera_id, payload.enabled)
    from app.services.ai_cognitive_log import NIVEL_INFO, NIVEL_SUCESSO, registrar_pensamento

    if payload.enabled:
        registrar_pensamento(
            f"Bem-Te-Vi Core (IA visual) ativado para a câmera '{row['name']}'.",
            nivel=NIVEL_SUCESSO,
            camera_id=camera_id,
        )
    else:
        registrar_pensamento(
            f"Bem-Te-Vi Core (IA visual) pausado para a câmera '{row['name']}' (economia de recursos).",
            nivel=NIVEL_INFO,
            camera_id=camera_id,
        )

    return CameraRepository.to_out(
        row,
        status=get_camera_manager().get_status(camera_id),
        night_mode=get_camera_manager().get_night_mode(camera_id),
    )


@router.patch("/{camera_id}/bioacoustics", response_model=CameraOut)
async def toggle_camera_bioacoustics(camera_id: str, payload: CameraBioacousticsToggle) -> CameraOut:
    """Ativa ou desativa a captura de áudio com BirdNET para esta câmera."""
    repo = _repo()
    existing = repo.get(camera_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    row = repo.update(camera_id, CameraUpdate(audio_enabled=payload.enabled))
    if row is None:
        raise HTTPException(status_code=404, detail="Camera not found")

    from app.services.audio_analysis import get_audio_analysis_service

    get_audio_analysis_service().trigger_reconcile()

    from app.services.ai_cognitive_log import NIVEL_INFO, NIVEL_SUCESSO, registrar_pensamento

    if payload.enabled:
        registrar_pensamento(
            f"Bioacústica (BirdNET) iniciada para a câmera '{row['name']}': monitorando cantos de aves.",
            nivel=NIVEL_SUCESSO,
            camera_id=camera_id,
        )
    else:
        registrar_pensamento(
            f"Bioacústica (BirdNET) pausada para a câmera '{row['name']}'.",
            nivel=NIVEL_INFO,
            camera_id=camera_id,
        )

    return CameraRepository.to_out(
        row,
        status=get_camera_manager().get_status(camera_id),
        night_mode=get_camera_manager().get_night_mode(camera_id),
    )


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(camera_id: str) -> None:
    try:
        get_pipeline_supervisor().stop_camera(camera_id)
        deleted = _repo().delete(camera_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Camera not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("delete_camera failed")
        raise HTTPException(status_code=500, detail="Failed to delete camera") from exc
