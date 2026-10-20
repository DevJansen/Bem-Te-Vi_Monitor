"""Rotas de mídia: streaming de clipes e geração de Reels verticais (9:16).

* ``GET /api/media/reel/{visit_id}`` — serve o Reel vertical gerado.
* ``POST /api/media/generate-reel/{visit_id}`` — gera (ou reaproveita) o Reel.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from app.core.rate_limiter import limiter
from app.services.reel_generator import generate_reel, remove_reel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media", tags=["media"])


@router.get("/reel/{visit_id}")
async def get_reel(visit_id: str) -> FileResponse:
    """Serve o Reel vertical (9:16) de uma visita."""
    import re

    # IDs de visita são UUIDs — valida para evitar path traversal.
    if not re.match(r"^[A-Za-z0-9_-]{1,100}$", visit_id):
        raise HTTPException(status_code=400, detail="ID inválido.")

    from app.core.config import get_settings

    reel_path = get_settings().captures_dir / "reels" / f"{visit_id}.mp4"
    if not reel_path.is_file():
        raise HTTPException(status_code=404, detail="Reel não encontrado.")
    return FileResponse(
        reel_path,
        media_type="video/mp4",
        filename=f"reel-{visit_id}.mp4",
    )


@router.post("/generate-reel/{visit_id}")
@limiter.limit("30/minute")
async def generate_reel_endpoint(
    request: Request,
    visit_id: str,
    force: bool = Query(default=False),
) -> dict:
    """Gera o Reel vertical (9:16) de uma visita e devolve a URL pública."""
    import re

    if not re.match(r"^[A-Za-z0-9_-]{1,100}$", visit_id):
        raise HTTPException(status_code=400, detail="ID inválido.")

    try:
        result = await run_in_threadpool(generate_reel, visit_id, force=force)
    except Exception as exc:
        logger.exception("generate_reel failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível gerar o Reel.",
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Clipe de vídeo não encontrado para esta visita.",
        )

    return {
        "visit_id": visit_id,
        "url": result["url"],
        "size_bytes": result["size_bytes"],
        "generated_at": result["generated_at"],
    }


@router.delete("/reel/{visit_id}")
def delete_reel_endpoint(visit_id: str) -> dict:
    """Remove o Reel gerado de uma visita."""
    import re

    if not re.match(r"^[A-Za-z0-9_-]{1,100}$", visit_id):
        raise HTTPException(status_code=400, detail="ID inválido.")
    remove_reel(visit_id)
    return {"removed": True}
