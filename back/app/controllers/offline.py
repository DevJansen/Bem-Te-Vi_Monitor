"""Rotas da área de importação e análise offline de vídeos (cartão de memória).

Endpoints:

- ``POST /api/offline/upload`` — recebe o vídeo, guarda em disco e dispara a
  análise em background, devolvendo o ``job_id`` imediatamente.
- ``GET  /api/offline/jobs`` — lista o estado de todos os jobs (em andamento e
  concluídos). É o que mantém a barra de progresso viva mesmo se o painel
  desconectar ou trocar de aba.
- ``GET  /api/offline/jobs/{job_id}`` — estado detalhado de um job.
- ``DELETE /api/offline/jobs/{job_id}`` — remove um job finalizado do histórico.
- ``POST /api/offline/jobs/clear`` — limpa todos os jobs finalizados.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.core.config import get_settings
from app.domain.models import OfflineJobOut
from app.infra.database.repository import CameraRepository
from app.services.offline_analysis import (
    ALLOWED_EXTENSIONS,
    MAX_RECORDING_BYTES,
    get_offline_analysis_service,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/offline", tags=["offline"])


def _parse_recorded_at(value: str | None) -> datetime:
    """Converte a data informada em um ``datetime`` UTC (ou usa 'agora')."""
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
    "/upload",
    response_model=OfflineJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_offline_video(
    camera_id: str = Form(...),
    recorded_at: str | None = Form(default=None),
    file: UploadFile = File(...),
) -> OfflineJobOut:
    """Recebe o vídeo e inicia a análise offline em background."""
    settings = get_settings()
    camera = CameraRepository(settings.db_path).get(camera_id)
    if camera is None:
        raise HTTPException(status_code=404, detail="A câmera selecionada não existe.")

    filename = Path((file.filename or "").replace("\\", "/")).name
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Formato não suportado. Envie um arquivo MP4, AVI, MOV ou MKV.",
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
        return get_offline_analysis_service().submit(
            camera_id=camera_id,
            camera_name=camera.get("name"),
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


@router.get("/jobs", response_model=list[OfflineJobOut])
async def list_offline_jobs() -> list[OfflineJobOut]:
    """Estado de todos os jobs, do mais recente ao mais antigo."""
    return get_offline_analysis_service().list_jobs()


@router.post("/jobs/clear")
async def clear_finished_offline_jobs() -> dict[str, int]:
    """Remove do histórico todos os jobs já finalizados."""
    removed = get_offline_analysis_service().clear_finished()
    return {"removed": removed}


@router.get("/jobs/{job_id}", response_model=OfflineJobOut)
async def get_offline_job(job_id: str) -> OfflineJobOut:
    result = get_offline_analysis_service().get(job_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Análise não encontrada; o histórico é mantido enquanto o "
            "backend está em execução.",
        )
    return result


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_offline_job(job_id: str) -> None:
    if not get_offline_analysis_service().delete(job_id):
        raise HTTPException(
            status_code=409,
            detail="Não é possível remover uma análise em andamento.",
        )
