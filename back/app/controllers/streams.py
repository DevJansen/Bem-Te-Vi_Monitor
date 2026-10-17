"""Endpoints de streams multi-câmera (Central de Câmeras / Alaris Core).

Dois recursos principais:

- ``GET /api/streams`` — estado em tempo real de cada câmera (status de conexão,
  FPS, backend de inferência, aves ativas no comedouro, pico de indivíduos).
  Alimenta os selos do grid multi-câmera.

- ``GET /api/stream/proxy/{camera_id}`` — **proxy seguro de vídeo** (MJPEG).
  O navegador recebe os quadros por esta rota e **nunca** vê a URL real nem as
  credenciais da câmera externa: o backend descriptografa em memória, abre o
  stream e retransmite os quadros. Zero vazamento de URL/senha no front-end.
"""

from __future__ import annotations

import asyncio
import logging

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.domain.models import StreamStatsOut
from app.infra.camera.manager import get_camera_manager
from app.infra.database.repository import CameraRepository
from app.infra.streams.registry import get_stream_registry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/streams", tags=["streams"])

# Entrega de quadros do proxy (~15 FPS).
_FRAME_INTERVAL_SEC = 0.066
_RETRY_SEC = 0.2
_placeholder: bytes | None = None


def _placeholder_jpeg() -> bytes:
    """Imagem escura de 'sem sinal' (gerada uma vez, em cache)."""
    global _placeholder
    if _placeholder is None:
        tela = np.zeros((240, 320, 3), dtype=np.uint8)
        tela[:] = (10, 15, 13)
        cv2.putText(
            tela,
            "Sem sinal",
            (70, 118),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (52, 211, 153),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            tela,
            "guardando conexao...",
            (52, 150),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (138, 163, 153),
            1,
            cv2.LINE_AA,
        )
        ok, buf = cv2.imencode(".jpg", tela, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        _placeholder = buf.tobytes() if ok else b""
    return _placeholder


@router.get("", response_model=list[StreamStatsOut])
def list_streams() -> list[StreamStatsOut]:
    """Estado em tempo real de cada stream (Alaris Core distribuído)."""
    try:
        repo = CameraRepository(get_settings().db_path)
        rows = {row["id"]: row for row in repo.list_all()}
        stats = get_stream_registry().all()
        saida: list[StreamStatsOut] = []
        for stat in stats:
            row = rows.get(stat.camera_id, {})
            saida.append(
                StreamStatsOut(
                    camera_id=stat.camera_id,
                    name=row.get("name") or stat.name,
                    location_label=row.get("location_label"),
                    source_type=row.get("source_type"),
                    is_active=bool(row.get("is_active", 1)),
                    status=stat.status,
                    fps=round(stat.fps, 1),
                    backend=stat.backend,
                    active_birds=stat.active_birds,
                    active_species=list(stat.active_species),
                    individuals_peak=stat.individuals_peak,
                    inferences=stat.inferences,
                    last_error=stat.last_error,
                )
            )
        return saida
    except Exception as exc:
        logger.exception("list_streams failed")
        raise HTTPException(
            status_code=500, detail="Falha ao listar os streams"
        ) from exc


async def _proxy_generator(camera_id: str):
    """Retransmite os quadros da câmera como MJPEG, sem expor credenciais."""
    manager = get_camera_manager()
    boundary = b"--frame"
    tentativas = 0

    while True:
        try:
            streamer = manager.get_streamer(camera_id)
            if streamer is None:
                streamer = await run_in_threadpool(manager.upsert_streamer, camera_id)
            if streamer is None:
                # Câmera inexistente/desativada: envia o placeholder.
                yield (
                    boundary
                    + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(_placeholder_jpeg())).encode("ascii")
                    + b"\r\n\r\n"
                    + _placeholder_jpeg()
                    + b"\r\n"
                )
                await asyncio.sleep(1.0)
                continue

            if streamer.status.value != "online" and tentativas < 5:
                await run_in_threadpool(streamer.open)
                tentativas += 1
                await asyncio.sleep(_RETRY_SEC)
                continue
            tentativas = 0

            frame = await run_in_threadpool(streamer.get_latest_annotated_frame)
            if frame is None:
                payload = _placeholder_jpeg()
            else:
                ok, buf = await run_in_threadpool(
                    cv2.imencode, ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 72]
                )
                payload = buf.tobytes() if ok else _placeholder_jpeg()
            yield (
                boundary
                + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(payload)).encode("ascii")
                + b"\r\n\r\n"
                + payload
                + b"\r\n"
            )
            await asyncio.sleep(_FRAME_INTERVAL_SEC)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Erro no proxy de stream camera=%s", camera_id)
            await asyncio.sleep(0.5)


@router.get("/proxy/{camera_id}")
async def stream_proxy(camera_id: str, request: Request) -> StreamingResponse:
    """Proxy MJPEG seguro: anonimiza a URL e as credenciais da câmera."""
    manager = get_camera_manager()
    streamer = manager.get_streamer(camera_id)
    if streamer is None:
        streamer = await run_in_threadpool(manager.upsert_streamer, camera_id)
    if streamer is None:
        raise HTTPException(
            status_code=404, detail="Câmera não encontrada ou desativada"
        )

    logger.debug(
        "Proxy de stream aberto camera=%s cliente=%s",
        camera_id,
        request.client.host if request.client else "desconhecido",
    )
    return StreamingResponse(
        _proxy_generator(camera_id),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Accel-Buffering": "no",
        },
    )
