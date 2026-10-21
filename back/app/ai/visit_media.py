"""Resolução segura das mídias tratadas de uma visita.

Centraliza a regra "qual é a melhor imagem desta captura?" usada por vários
módulos do Bem-Te-Vi Core (assinaturas visuais, aprendizado ativo, auto-associação
de espécie e exportação HD). A ordem de preferência é:

1. **Recorte tratado** (``metadata.crop_path``) — close-up da ave, já passou
   pelo pipeline de melhoria (CLAHE, redução de ruído e nitidez).
2. **Recorte canônico** (``crops/{visit_id}.jpg``) — usado quando o metadado
   não foi gravado (visitas antigas ou migrações).
3. **Thumbnail oficial** (``captures/{thumbnail_path}``) — quadro completo em
   alta definição, útil quando não houve recorte.

Todos os caminhos são validados contra as pastas de mídia do ``app-data``,
impedindo *path traversal* mesmo que o banco contenha um caminho malicioso ou
corrompido. Nenhuma exceção é propagada: a ausência de mídia apenas devolve
``None`` e o chamador decide como degradar.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


def _metadata_of(row: dict[str, Any]) -> dict[str, Any]:
    """Lê o ``metadata_json`` da visita de forma tolerante a falhas."""
    try:
        metadata = json.loads(row.get("metadata_json") or "{}")
    except (TypeError, ValueError):
        return {}
    return metadata if isinstance(metadata, dict) else {}


def _inside(path: Path, root: Path) -> bool:
    """Confere se ``path`` está contido em ``root`` (comparação resolvida)."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def read_visit_metadata(row: dict[str, Any]) -> dict[str, Any]:
    """Lê o ``metadata_json`` de uma visita de forma tolerante a falhas."""
    return _metadata_of(row)


def resolve_crop_path(
    visit_id: str, settings: Settings | None = None
) -> Path | None:
    """Recorte canônico (``crops/{visit_id}.jpg``), se existir."""
    settings = settings or get_settings()
    candidate = (settings.crops_dir / f"{visit_id}.jpg").resolve()
    if candidate.parent != settings.crops_dir.resolve():
        return None
    return candidate if candidate.is_file() else None


def resolve_visit_image(
    row: dict[str, Any], settings: Settings | None = None
) -> Path | None:
    """Melhor imagem tratada disponível para a visita (recorte > thumbnail)."""
    settings = settings or get_settings()
    metadata = _metadata_of(row)

    crop_relative = metadata.get("crop_path")
    if isinstance(crop_relative, str) and crop_relative.strip():
        candidate = (settings.app_data_dir / crop_relative).resolve()
        if _inside(candidate, settings.app_data_dir.resolve()) and candidate.is_file():
            return candidate

    canonical = resolve_crop_path(str(row.get("id") or ""), settings)
    if canonical is not None:
        return canonical

    thumbnail = row.get("thumbnail_path")
    if thumbnail:
        normalized = str(thumbnail).replace("\\", "/").lstrip("/")
        candidate = (settings.captures_dir / normalized).resolve()
        if _inside(candidate, settings.captures_dir.resolve()) and candidate.is_file():
            return candidate
    return None


def resolve_visit_image_with_source(
    row: dict[str, Any], settings: Settings | None = None
) -> tuple[Path, str] | None:
    """Como :func:`resolve_visit_image`, mas devolve também a origem.

    A origem é ``"recorte"`` ou ``"thumbnail"`` — o mesmo vocabulário usado pela
    identificação externa e exibido na ficha da visita.
    """
    settings = settings or get_settings()
    metadata = _metadata_of(row)

    crop_relative = metadata.get("crop_path")
    if isinstance(crop_relative, str) and crop_relative.strip():
        candidate = (settings.app_data_dir / crop_relative).resolve()
        if _inside(candidate, settings.app_data_dir.resolve()) and candidate.is_file():
            return candidate, "recorte"

    canonical = resolve_crop_path(str(row.get("id") or ""), settings)
    if canonical is not None:
        return canonical, "recorte"

    thumbnail = row.get("thumbnail_path")
    if thumbnail:
        normalized = str(thumbnail).replace("\\", "/").lstrip("/")
        candidate = (settings.captures_dir / normalized).resolve()
        if _inside(candidate, settings.captures_dir.resolve()) and candidate.is_file():
            return candidate, "thumbnail"
    return None
