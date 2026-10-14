"""Local media storage helpers for clips and thumbnails."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def relative_to_captures(path: Path) -> str:
    settings = get_settings()
    try:
        rel = path.resolve().relative_to(settings.captures_dir.resolve())
        return str(rel).replace("\\", "/")
    except Exception:
        return path.name


def save_thumbnail(frame: np.ndarray, camera_id: str, visit_id: str) -> Path | None:
    settings = get_settings()
    settings.ensure_directories()
    out = settings.thumbs_dir / f"{camera_id}_{visit_id}_{_stamp()}.jpg"
    try:
        ok = cv2.imwrite(str(out), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            logger.error("Failed to write thumbnail %s", out)
            return None
        return out
    except Exception:
        logger.exception("Thumbnail save error")
        return None


def save_bird_crop(
    frame: np.ndarray,
    bbox: tuple[float, float, float, float],
    visit_id: str,
) -> str | None:
    """Salva o recorte da ave em app-data/crops e retorna seu caminho relativo."""
    settings = get_settings()
    try:
        settings.ensure_directories()
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = bbox
        left = max(0, min(width, int(x1)))
        top = max(0, min(height, int(y1)))
        right = max(0, min(width, int(np.ceil(x2))))
        bottom = max(0, min(height, int(np.ceil(y2))))
        if right <= left or bottom <= top:
            logger.warning("Invalid bird bounding box for crop visit=%s", visit_id)
            return None

        crop = frame[top:bottom, left:right]
        if crop.size == 0:
            logger.warning("Empty bird crop for visit=%s", visit_id)
            return None
        max_dimension = 1024
        crop_height, crop_width = crop.shape[:2]
        scale = min(1.0, max_dimension / max(crop_width, crop_height))
        if scale < 1.0:
            crop = cv2.resize(
                crop,
                (
                    max(1, round(crop_width * scale)),
                    max(1, round(crop_height * scale)),
                ),
                interpolation=cv2.INTER_AREA,
            )

        output_path = settings.crops_dir / f"{visit_id}.jpg"
        if not cv2.imwrite(
            str(output_path),
            crop,
            [int(cv2.IMWRITE_JPEG_QUALITY), 85],
        ):
            logger.error("Failed to write bird crop %s", output_path)
            return None
        return output_path.relative_to(settings.app_data_dir).as_posix()
    except Exception:
        logger.exception("Bird crop save error visit=%s", visit_id)
        return None


def save_clip_mp4(
    frames: list[np.ndarray],
    camera_id: str,
    visit_id: str,
    fps: float,
) -> Path | None:
    if not frames:
        return None
    settings = get_settings()
    settings.ensure_directories()
    out = settings.clips_dir / f"{camera_id}_{visit_id}_{_stamp()}.mp4"
    try:
        height, width = frames[0].shape[:2]
        fps = max(float(fps), 1.0)
        # Prefer mp4v; fall back to avi/mjpg if needed
        writers = [
            (out, "mp4v"),
            (out.with_suffix(".avi"), "XVID"),
        ]
        for path, fourcc_name in writers:
            fourcc = cv2.VideoWriter_fourcc(*fourcc_name)
            writer = cv2.VideoWriter(str(path), fourcc, fps, (width, height))
            if not writer.isOpened():
                writer.release()
                continue
            for frame in frames:
                if frame is None or frame.size == 0:
                    continue
                if frame.shape[0] != height or frame.shape[1] != width:
                    frame = cv2.resize(frame, (width, height))
                writer.write(frame)
            writer.release()
            if path.exists() and path.stat().st_size > 0:
                return path
        logger.error("Unable to open any VideoWriter for visit %s", visit_id)
        return None
    except Exception:
        logger.exception("Clip save error")
        return None
