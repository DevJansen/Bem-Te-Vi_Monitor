"""MJPEG video feed endpoints (local streams only)."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from app.infra.camera.manager import get_camera_manager
from app.infra.camera.streamer import StreamStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/video-feed", tags=["video-feed"])


def _mjpeg_generator(camera_id: str, *, boxes: bool):
    """
    Stream MJPEG com frames JPEG já anotados (YOLOv8) quando boxes=True.

    Lê do cache do CameraStreamer (preenchido pelo pipeline) para não
    competir com VideoCapture.read().
    """
    manager = get_camera_manager()
    boundary = b"--frame"
    idle_opens = 0

    while True:
        try:
            streamer = manager.get_streamer(camera_id)
            if streamer is None:
                streamer = manager.upsert_streamer(camera_id)
            if streamer is None:
                time.sleep(1.0)
                continue

            if streamer.status != StreamStatus.ONLINE:
                if idle_opens < 3:
                    streamer.open()
                    idle_opens += 1
                time.sleep(0.3)
                continue

            idle_opens = 0
            jpeg = streamer.snapshot_jpeg(quality=72, annotated=boxes)
            if jpeg is None and boxes:
                # Fallback: frame cru se ainda não houver anotação
                jpeg = streamer.snapshot_jpeg(quality=72, annotated=False)
            if jpeg is None:
                time.sleep(0.15)
                continue

            yield (
                boundary
                + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(jpeg)).encode("ascii")
                + b"\r\n\r\n"
                + jpeg
                + b"\r\n"
            )
            time.sleep(0.066)  # ~15 FPS de entrega
        except GeneratorExit:
            break
        except Exception:
            logger.exception("MJPEG generator error camera=%s", camera_id)
            time.sleep(0.5)


@router.get("/{camera_id}")
async def video_feed(
    camera_id: str,
    boxes: bool = Query(
        default=True,
        description="Se true, envia frames com bounding boxes YOLOv8 desenhadas",
    ),
) -> StreamingResponse:
    manager = get_camera_manager()
    streamer = manager.get_streamer(camera_id) or manager.upsert_streamer(camera_id)
    if streamer is None:
        raise HTTPException(status_code=404, detail="Camera not found or disabled")

    return StreamingResponse(
        _mjpeg_generator(camera_id, boxes=boxes),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@router.get("/{camera_id}/snapshot")
async def snapshot(
    camera_id: str,
    boxes: bool = Query(default=True),
) -> Response:
    manager = get_camera_manager()
    streamer = manager.get_streamer(camera_id) or manager.upsert_streamer(camera_id)
    if streamer is None:
        raise HTTPException(status_code=404, detail="Camera not found or disabled")

    jpeg = streamer.snapshot_jpeg(quality=85, annotated=boxes)
    if jpeg is None and streamer.status != StreamStatus.ONLINE:
        try:
            streamer.open()
            ok, _ = streamer.read()
            if ok:
                jpeg = streamer.snapshot_jpeg(quality=85, annotated=boxes)
        except Exception:
            logger.exception("Snapshot open/read failed for %s", camera_id)

    if jpeg is None:
        raise HTTPException(status_code=503, detail="No frame available")
    return Response(content=jpeg, media_type="image/jpeg")
