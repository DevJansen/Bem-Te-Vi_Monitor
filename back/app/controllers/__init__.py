"""HTTP controllers / route handlers."""

from fastapi import APIRouter

from app.api import analytics
from app.controllers import (
    anomalies,
    audio_detections,
    cameras,
    events,
    offline,
    settings,
    species,
    stats,
    video_feed,
    videos,
    visits,
    weather,
)

api_router = APIRouter()
api_router.include_router(anomalies.router)
api_router.include_router(audio_detections.router)
api_router.include_router(events.router)
api_router.include_router(cameras.router)
api_router.include_router(visits.router)
api_router.include_router(species.router)
api_router.include_router(offline.router)
api_router.include_router(settings.router)
api_router.include_router(stats.router)
api_router.include_router(analytics.router)
api_router.include_router(video_feed.router)
api_router.include_router(videos.router)
api_router.include_router(weather.router)

__all__ = ["api_router"]
