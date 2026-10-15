"""Streaming local de vídeos (clipes das visitas) com suporte a Range.

Os clipes ficam em `app-data/captures/clips/`. Este endpoint entrega o arquivo
com o `Content-Type` correto e suporte a requisições de intervalo (`Range`),
essencial para o player HTML5 avançar/rebobinar um MP4 sem baixá-lo por inteiro.

O `FileResponse` do Starlette já responde a `Range` com status `206` e o header
`Content-Range`, além de enviar `Accept-Ranges: bytes` e `Content-Length`.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/videos", tags=["videos"])

# Extensões aceitas e o respectivo MIME type para o player do navegador.
_MIME_BY_SUFFIX: dict[str, str] = {
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
}


def _resolve_clip(filename: str) -> Path:
    """Resolve o caminho do clipe garantindo que fique dentro de `clips/`.

    Bloqueia path traversal (por exemplo `../` ou caminhos absolutos) e aceita
    apenas extensões de vídeo conhecidas.
    """
    # Aceita somente o nome do arquivo, sem diretórios.
    if not filename or filename != Path(filename).name:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")
    if filename in {".", ".."} or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Nome de arquivo inválido")

    suffix = Path(filename).suffix.lower()
    if suffix not in _MIME_BY_SUFFIX:
        raise HTTPException(
            status_code=415,
            detail="Formato de vídeo não suportado",
        )

    clips_dir = get_settings().clips_dir.resolve()
    candidate = (clips_dir / filename).resolve()
    # Garante que o arquivo resolvido está diretamente dentro de clips/.
    if candidate.parent != clips_dir:
        raise HTTPException(status_code=400, detail="Caminho inválido")
    return candidate


@router.get("/{filename}")
async def get_video(filename: str) -> FileResponse:
    """Entrega o clipe de vídeo, suportando requisições parciais (Range)."""
    path = _resolve_clip(filename)

    if not path.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")

    try:
        size = path.stat().st_size
    except OSError as exc:
        logger.exception("Falha ao acessar o clipe %s", path)
        raise HTTPException(
            status_code=500,
            detail="Não foi possível ler o arquivo de vídeo",
        ) from exc

    if size == 0:
        raise HTTPException(
            status_code=404,
            detail="Arquivo de vídeo vazio ou corrompido",
        )

    media_type = _MIME_BY_SUFFIX[path.suffix.lower()]
    return FileResponse(
        str(path),
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, max-age=86400",
        },
    )
