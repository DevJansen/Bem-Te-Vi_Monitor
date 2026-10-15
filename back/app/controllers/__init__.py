"""HTTP controllers / route handlers."""

from fastapi import APIRouter

from app.api import analytics
from app.controllers import (
    audio_detections,
    cameras,
    events,
    recordings,
    settings,
    species,
    stats,
    video_feed,
    videos,
    visits,
)

api_router = APIRouter()
api_router.include_router(audio_detections.router)
api_router.include_router(events.router)
api_router.include_router(cameras.router)
api_router.include_router(visits.router)
api_router.include_router(species.router)
api_router.include_router(recordings.router)
api_router.include_router(settings.router)
api_router.include_router(stats.router)
api_router.include_router(analytics.router)
api_router.include_router(video_feed.router)
api_router.include_router(videos.router)

__all__ = ["api_router"]
