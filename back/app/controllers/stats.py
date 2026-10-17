"""REST routes for dashboard statistics."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.domain.models import StatsOut
from app.infra.camera.manager import get_camera_manager
from app.infra.database.repository import VisitRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
async def get_stats(
    camera_id: str | None = Query(
        default=None, description="Restringe as métricas a um jardim (câmera)."
    ),
) -> StatsOut:
    try:
        raw = VisitRepository(get_settings().db_path).stats(camera_id=camera_id)
        # Prefer live streamer count when available
        live = len(get_camera_manager().list_info())
        if live:
            raw["active_cameras"] = live
        return StatsOut(
            total_visits=raw["total_visits"],
            visits_today=raw["visits_today"],
            active_cameras=raw["active_cameras"],
            total_cameras=raw["total_cameras"],
            species_counts=raw["species_counts"],
            visits_by_hour=raw["visits_by_hour"],
            last_visit_at=raw["last_visit_at"],
            visitors_today=raw.get("visitors_today", 0),
            squirrel_visits_today=raw.get("squirrel_visits_today", 0),
            seeds_stolen_today=raw.get("seeds_stolen_today", 0),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        logger.exception("get_stats failed")
        raise HTTPException(status_code=500, detail="Failed to compute stats") from exc
