"""HTTP controllers / route handlers."""

from fastapi import APIRouter

from app.api import analytics
from app.controllers import (
    ai,
    anomalies,
    audio_detections,
    bioacoustics,
    cameras,
    events,
    gallery,
    offline,
    settings,
    species,
    stats,
    streams,
    video_feed,
    videos,
    visits,
    weather,
    wildlife,
)

api_router = APIRouter()
api_router.include_router(ai.router)
api_router.include_router(streams.router)
api_router.include_router(anomalies.router)
api_router.include_router(audio_detections.router)
api_router.include_router(events.router)
api_router.include_router(cameras.router)
api_router.include_router(gallery.router)
api_router.include_router(visits.router)
api_router.include_router(species.router)
api_router.include_router(offline.router)
api_router.include_router(settings.router)
api_router.include_router(stats.router)
api_router.include_router(analytics.router)
api_router.include_router(video_feed.router)
api_router.include_router(videos.router)
api_router.include_router(weather.router)
api_router.include_router(wildlife.router)
api_router.include_router(bioacoustics.router)

__all__ = ["api_router"]
