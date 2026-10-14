"""Routes for importing and tracking offline video analyses."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.domain.models import RecordingAnalysisOut
from app.infra.database.repository import CameraRepository
from app.services.recording_analysis import (
    ALLOWED_EXTENSIONS,
    MAX_RECORDING_BYTES,
    get_recording_analysis_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/recordings", tags=["recordings"])


def _parse_recorded_at(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail="A data da gravação informada é inválida.",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@router.post(
    "/import",
    response_model=RecordingAnalysisOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_recording(
    camera_id: str = Form(...),
    recorded_at: str | None = Form(default=None),
    file: UploadFile = File(...),
) -> RecordingAnalysisOut:
    settings = get_settings()
    if CameraRepository(settings.db_path).get(camera_id) is None:
        raise HTTPException(status_code=404, detail="A câmera selecionada não existe.")

    filename = Path((file.filename or "").replace("\\", "/")).name
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Formato não suportado. Envie um arquivo MP4, AVI ou MKV.",
        )
    source_datetime = _parse_recorded_at(recorded_at)
    import_dir = settings.app_data_dir / "imports"
    import_dir.mkdir(parents=True, exist_ok=True)
    upload_path = import_dir / f"{uuid.uuid4()}{extension}"

    total_bytes = 0
    try:
        with upload_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                total_bytes += len(chunk)
                if total_bytes > MAX_RECORDING_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="O vídeo excede o limite de 2 GB.",
                    )
                destination.write(chunk)
    except HTTPException:
        upload_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        upload_path.unlink(missing_ok=True)
        logger.exception("Failed to store uploaded recording")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível armazenar o vídeo para análise.",
        ) from exc
    finally:
        await file.close()

    if total_bytes == 0:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="O arquivo de vídeo está vazio.")

    try:
        return get_recording_analysis_service().submit(
            camera_id=camera_id,
            filename=filename,
            path=upload_path,
            recorded_at=source_datetime,
        )
    except RuntimeError as exc:
        upload_path.unlink(missing_ok=True)
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        upload_path.unlink(missing_ok=True)
        logger.exception("Failed to queue uploaded recording")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível iniciar a análise do vídeo.",
        ) from exc


@router.get("/{analysis_id}", response_model=RecordingAnalysisOut)
async def get_recording_analysis(analysis_id: str) -> RecordingAnalysisOut:
    result = get_recording_analysis_service().get(analysis_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Análise não encontrada; o histórico é mantido enquanto o backend está em execução.",
        )
    return result
