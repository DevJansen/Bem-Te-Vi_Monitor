"""REST routes for BirdNET audio detections."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.domain.models import (
    AudioAnalysisStatusOut,
    AudioDetectionOut,
    AudioInputDevicesOut,
)
from app.infra.database.audio_repository import AudioDetectionRepository
from app.infra.database.repository import SettingsRepository
from app.services.audio_analysis import get_audio_analysis_service
from app.services.audio_devices import build_audio_input_devices

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/audio-detections", tags=["audio"])


@router.get("", response_model=list[AudioDetectionOut])
def list_audio_detections(
    limit: int = Query(default=30, ge=1, le=200),
) -> list[AudioDetectionOut]:
    try:
        rows = AudioDetectionRepository(get_settings().db_path).list_recent(limit)
        return [AudioDetectionOut(**row) for row in rows]
    except Exception as exc:
        logger.exception("list_audio_detections failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar as detecções sonoras.",
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
