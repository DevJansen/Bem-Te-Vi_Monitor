"""Safe removal of visit rows and only their managed media files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings, get_settings
from app.infra.database.repository import VisitRepository

logger = logging.getLogger(__name__)


def _managed_media_path(relative_path: str, settings: Settings) -> Path:
    normalized = relative_path.replace("\\", "/")
    candidate = Path(normalized)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Caminho de mídia fora dos diretórios permitidos.")

    if candidate.parts and candidate.parts[0] == "captures":
        root = settings.captures_dir.resolve()
        candidate = settings.app_data_dir / candidate
    elif candidate.parts and candidate.parts[0] == "crops":
        root = settings.crops_dir.resolve()
        candidate = settings.app_data_dir / candidate
    else:
        root = settings.captures_dir.resolve()
        candidate = settings.captures_dir / candidate

    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("Caminho de mídia fora dos diretórios permitidos.") from exc
    return candidate


def _visit_media_paths(row: dict[str, Any], settings: Settings) -> set[Path]:
    paths: set[Path] = set()
    for value in (row.get("thumbnail_path"), row.get("clip_path")):
        if value:
            paths.add(_managed_media_path(str(value), settings))

    try:
        metadata = json.loads(row.get("metadata_json") or "{}")
    except (TypeError, ValueError):
        logger.warning("Invalid visit metadata while deleting visit=%s", row.get("id"))
        metadata = {}
    crop_path = metadata.get("crop_path") if isinstance(metadata, dict) else None
    if crop_path:
        paths.add(_managed_media_path(str(crop_path), settings))
    return paths


def delete_visit_media_and_record(
    visit_id: str,
    *,
    repository: VisitRepository | None = None,
    settings: Settings | None = None,
) -> int | None:
    settings = settings or get_settings()
    repository = repository or VisitRepository(settings.db_path)
    row = repository.get(visit_id)
    if row is None:
        return None

    media_paths = _visit_media_paths(row, settings)
    removed_files = 0
    for path in media_paths:
        try:
            if path.is_file():
                path.unlink()
                removed_files += 1
            elif path.exists():
                raise OSError("O caminho associado não é um arquivo regular.")
        except OSError:
            logger.exception("Failed to remove visit media visit=%s", visit_id)
            raise

    if not repository.delete(visit_id):
        raise RuntimeError("O registro foi removido durante a operação.")
    return removed_files


def delete_visits_before(
    detected_before: str,
    *,
    repository: VisitRepository | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repository = repository or VisitRepository(settings.db_path)
    rows = repository.list_before(detected_before)
    deleted = 0
    media_deleted = 0
    failed: list[str] = []
    for row in rows:
        try:
            removed = delete_visit_media_and_record(
                row["id"],
                repository=repository,
                settings=settings,
            )
            if removed is not None:
                deleted += 1
                media_deleted += removed
        except (OSError, RuntimeError, ValueError):
            logger.exception("Failed to delete old visit=%s", row["id"])
            failed.append(row["id"])
    return {
        "deleted_records": deleted,
        "deleted_media_files": media_deleted,
        "failed_records": failed,
    }


def delete_all_visits(
    *,
    repository: VisitRepository | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    repository = repository or VisitRepository(settings.db_path)
    rows = repository.list(limit=2_147_483_647, offset=0)
    deleted = 0
    media_deleted = 0
    failed: list[str] = []
    failed_media: list[str] = []
    for row in rows:
        try:
            removed = delete_visit_media_and_record(
                row["id"],
                repository=repository,
                settings=settings,
            )
            if removed is not None:
                deleted += 1
                media_deleted += removed
        except (OSError, RuntimeError, ValueError):
            logger.exception(
                "Failed to delete visit during history reset visit=%s",
                row["id"],
            )
            failed.append(row["id"])
    if not failed:
        media_dirs = (
            (settings.thumbs_dir, {".jpg", ".jpeg", ".png"}),
            (settings.clips_dir, {".mp4", ".avi", ".mkv"}),
            (settings.crops_dir, {".jpg", ".jpeg", ".png"}),
        )
        for directory, extensions in media_dirs:
            if not directory.exists():
                continue
            for path in directory.iterdir():
                if path.suffix.lower() not in extensions or not path.is_file():
                    continue
                try:
                    path.unlink()
                    media_deleted += 1
                except OSError:
                    logger.exception("Failed to remove media during history reset: %s", path)
                    failed_media.append(path.name)
    return {
        "deleted_records": deleted,
        "deleted_media_files": media_deleted,
        "failed_records": failed,
        "failed_media_files": failed_media,
    }
