"""REST routes for camera management."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.core.config import get_settings
from app.domain.models import CameraCreate, CameraOut, CameraUpdate, CameraZones
from app.infra.ai.pipeline import get_pipeline_supervisor
from app.infra.camera.crypto import encrypt_secret
from app.infra.camera.manager import get_camera_manager
from app.infra.database.repository import CameraRepository

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
async def create_camera(payload: CameraCreate) -> CameraOut:
    try:
        row = _repo().create(
            payload,
            username_enc=encrypt_secret(payload.username),
            password_enc=encrypt_secret(payload.password),
        )
        if row["enabled"]:
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
                username_enc = existing.get("username_enc")
            if payload.password is None:
                password_enc = existing.get("password_enc")

        row = _repo().update(
            camera_id,
            payload,
            username_enc=username_enc,
            password_enc=password_enc,
            update_credentials=update_creds,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Camera not found")

        get_pipeline_supervisor().restart_camera(camera_id)
        return CameraRepository.to_out(
            row, status=get_camera_manager().get_status(camera_id)
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("update_camera failed")
        raise HTTPException(status_code=500, detail="Failed to update camera") from exc


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
