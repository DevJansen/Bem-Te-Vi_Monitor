"""Endpoints de transmissão MJPEG (apenas streams locais).

O painel React exibe o vídeo ao vivo com uma tag ``<img>`` apontando para
``/api/video-feed/{camera_id}``. Diferente de um arquivo comum, um stream MJPEG
mantém a conexão HTTP aberta enquanto o ``<img>`` existir.

Quando o usuário troca de aba, o componente é desmontado e o navegador fecha o
``<img>``. Se o servidor não encerrar o gerador na hora, a conexão vira um
"zumbi": continua ocupando uma thread do pool e, ao voltar para o painel, a nova
requisição fica presa atrás das antigas (esgotamento do limite de conexões do
navegador) — sintoma clássico de "precisa dar F5".

Por isso o gerador aqui é **assíncrono**: o Starlette o cancela de forma limpa
assim que o cliente desconecta, liberando o recurso imediatamente. As chamadas
bloqueantes do OpenCV são despachadas para um *threadpool* para não travar o
laço de eventos.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.infra.camera.manager import get_camera_manager
from app.infra.camera.streamer import StreamStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/video-feed", tags=["video-feed"])

# Intervalo entre quadros entregues ao navegador (~15 FPS de entrega).
_FRAME_INTERVAL_SEC = 0.066
# Espera entre tentativas de reabrir a câmera quando ela ainda não está online.
_OPEN_RETRY_SEC = 0.3
# Máximo de tentativas de abertura por conexão (evita laço agressivo).
_MAX_OPEN_ATTEMPTS = 3

# Contagem de transmissões MJPEG ativas por câmera (ajuda a detectar zumbis).
_active_feeds: dict[str, int] = defaultdict(int)
_active_feeds_lock = threading.Lock()


def _register_feed(camera_id: str) -> int:
    """Incrementa e devolve o total de transmissões ativas da câmera."""
    with _active_feeds_lock:
        _active_feeds[camera_id] += 1
        return _active_feeds[camera_id]


def _unregister_feed(camera_id: str) -> int:
    """Decrementa e devolve o total de transmissões ativas da câmera."""
    with _active_feeds_lock:
        _active_feeds[camera_id] = max(_active_feeds.get(camera_id, 0) - 1, 0)
        return _active_feeds[camera_id]


def active_feed_count(camera_id: str) -> int:
    """Quantidade de transmissões MJPEG abertas para a câmera (diagnóstico)."""
    with _active_feeds_lock:
        return _active_feeds.get(camera_id, 0)


async def _mjpeg_generator(camera_id: str, *, boxes: bool):
    """Gerador assíncrono que entrega quadros JPEG no formato MJPEG.

    Lê do cache do ``CameraStreamer`` (alimentado pelo pipeline) para não
    competir com ``VideoCapture.read()``. Por ser assíncrono, é interrompido de
    imediato quando o cliente desconecta (troca de aba, F5, fechamento do
    painel), evitando conexões zumbis que esgotam o pool de threads.
    """
    manager = get_camera_manager()
    boundary = b"--frame"
    open_attempts = 0
    total = _register_feed(camera_id)
    logger.info("Stream MJPEG aberto camera=%s (ativas=%d)", camera_id, total)

    try:
        while True:
            try:
                streamer = manager.get_streamer(camera_id)
                if streamer is None:
                    streamer = await run_in_threadpool(
                        manager.upsert_streamer, camera_id
                    )
                if streamer is None:
                    await asyncio.sleep(1.0)
                    continue

                if streamer.status != StreamStatus.ONLINE:
                    # A câmera ainda não está pronta: tenta abri-la algumas vezes
                    # sem bloquear o laço de eventos (open() é síncrono).
                    if open_attempts < _MAX_OPEN_ATTEMPTS:
                        await run_in_threadpool(streamer.open)
                        open_attempts += 1
                    await asyncio.sleep(_OPEN_RETRY_SEC)
                    continue

                open_attempts = 0
                jpeg = await run_in_threadpool(
                    streamer.snapshot_jpeg, 72, annotated=boxes
                )
                if jpeg is None and boxes:
                    # Enquanto a anotação não existe, envia o quadro cru.
                    jpeg = await run_in_threadpool(
                        streamer.snapshot_jpeg, 72, annotated=False
                    )
                if jpeg is None:
                    await asyncio.sleep(0.15)
                    continue

                yield (
                    boundary
                    + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(jpeg)).encode("ascii")
                    + b"\r\n\r\n"
                    + jpeg
                    + b"\r\n"
                )
                await asyncio.sleep(_FRAME_INTERVAL_SEC)
            except asyncio.CancelledError:
                # Cliente desconectou: propaga para encerrar o gerador.
                raise
            except Exception:
                logger.exception("Erro no gerador MJPEG camera=%s", camera_id)
                await asyncio.sleep(0.5)
    finally:
        restantes = _unregister_feed(camera_id)
        logger.info(
            "Stream MJPEG encerrado camera=%s (ativas=%d)", camera_id, restantes
        )


@router.get("/{camera_id}")
async def video_feed(
    camera_id: str,
    request: Request,
    boxes: bool = Query(
        default=True,
        description="Se true, envia quadros com as caixas do YOLOv8 desenhadas",
    ),
) -> StreamingResponse:
    """Transmite o vídeo da câmera como MJPEG (multipart/x-mixed-replace)."""
    manager = get_camera_manager()
    streamer = manager.get_streamer(camera_id)
    if streamer is None:
        streamer = await run_in_threadpool(manager.upsert_streamer, camera_id)
    if streamer is None:
        raise HTTPException(
            status_code=404, detail="Câmera não encontrada ou desativada"
        )

    logger.debug(
        "Nova conexão MJPEG camera=%s cliente=%s",
        camera_id,
        request.client.host if request.client else "desconhecido",
    )

    return StreamingResponse(
        _mjpeg_generator(camera_id, boxes=boxes),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            # Impede que proxies (Vite/nginx) segurem os quadros em buffer.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{camera_id}/snapshot")
async def snapshot(
    camera_id: str,
    boxes: bool = Query(default=True),
) -> Response:
    manager = get_camera_manager()
    streamer = manager.get_streamer(camera_id)
    if streamer is None:
        streamer = await run_in_threadpool(manager.upsert_streamer, camera_id)
    if streamer is None:
        raise HTTPException(
            status_code=404, detail="Câmera não encontrada ou desativada"
        )

    jpeg = await run_in_threadpool(streamer.snapshot_jpeg, 85, annotated=boxes)
    if jpeg is None and streamer.status != StreamStatus.ONLINE:
        try:
            await run_in_threadpool(streamer.open)
            ok, _ = await run_in_threadpool(streamer.read)
            if ok:
                jpeg = await run_in_threadpool(
                    streamer.snapshot_jpeg, 85, annotated=boxes
                )
        except Exception:
            logger.exception("Falha ao abrir/ler snapshot de %s", camera_id)

    if jpeg is None:
        raise HTTPException(status_code=503, detail="Nenhum quadro disponível")
    return Response(content=jpeg, media_type="image/jpeg")
