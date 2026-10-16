"""Rotas REST do motor de IA (AI Core).

Expõe o "coração pulsante" do AviaWatch: o estado do modelo, a telemetria de
desempenho (FPS, latência, inferências) e o **log cognitivo** — os "pensamentos"
da IA em tempo real, consumidos pelo painel futurista do Dashboard.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.core.config import get_settings
from app.domain.models import (
    AiEngineOut,
    AiLogOut,
    AiLogsOut,
    AiPerformanceOut,
    AiResourcesOut,
    AiStatusOut,
    AiThroughputOut,
)
from app.infra.camera.manager import get_camera_manager
from app.infra.database.repository import CameraRepository
from app.services.ai_cognitive_log import get_cognitive_log
from app.services.ai_telemetry import get_ai_telemetry

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status", response_model=AiStatusOut)
def ai_status() -> AiStatusOut:
    """Estado atual do motor de IA, recursos e métricas de desempenho."""
    try:
        telemetria = get_ai_telemetry()
        retrato = telemetria.snapshot()

        # Modelo: nome/backend vêm do detector; o limiar ativo, do detector.
        modelo = dict(retrato.get("model") or {})
        confianca_ativa: float | None = None
        try:
            from app.infra.ai.detector import get_bird_detector

            detector = get_bird_detector()
            confianca_ativa = float(detector.confidence)
            if detector.backend and not modelo.get("backend"):
                modelo["backend"] = detector.backend
        except Exception:
            logger.debug("Detector indisponível para o status da IA", exc_info=True)

        # Câmeras: habilitadas (DB) e online (manager de streams).
        cameras_enabled = 0
        cameras_online = 0
        try:
            repo = CameraRepository(get_settings().db_path)
            cameras_enabled = sum(1 for row in repo.list_all() if row["enabled"])
            status_map = get_camera_manager().status_map()
            cameras_online = sum(
                1 for status in status_map.values() if status == "online"
            )
        except Exception:
            logger.debug("Falha ao contar câmeras", exc_info=True)

        return AiStatusOut(
            engine=AiEngineOut(
                state=retrato.get("state") or "Aguardando stream",
                model=modelo.get("model"),
                backend=modelo.get("backend"),
                device=modelo.get("device"),
                imgsz=modelo.get("imgsz"),
                confidence=confianca_ativa,
                notes=list(modelo.get("notes") or []),
            ),
            throughput=AiThroughputOut(**(retrato.get("throughput") or {})),
            performance=AiPerformanceOut(**(retrato.get("performance") or {})),
            resources=AiResourcesOut(**(retrato.get("resources") or {})),
            cameras_enabled=cameras_enabled,
            cameras_online=cameras_online,
            uptime_seconds=float(retrato.get("uptime_seconds") or 0.0),
            started_at=retrato.get("started_at"),
        )
    except Exception as exc:
        logger.exception("ai_status failed")
        raise HTTPException(
            status_code=500, detail="Falha ao obter o status da IA"
        ) from exc


@router.get("/logs", response_model=AiLogsOut)
def ai_logs(
    limit: int = Query(default=60, ge=1, le=400),
    since_id: int | None = Query(
        default=None,
        ge=0,
        description="Devolve apenas eventos mais novos que este id (polling incremental).",
    ),
) -> AiLogsOut:
    """Log cognitivo da IA (os "pensamentos" mais recentes, em ordem cronológica)."""
    try:
        log = get_cognitive_log()
        eventos = log.listar(limit=limit, since_id=since_id)
        return AiLogsOut(
            entries=[
                AiLogOut(
                    id=evento.id,
                    timestamp=evento.timestamp,
                    hora=evento.hora,
                    level=evento.nivel,
                    source=evento.origem,
                    message=evento.mensagem,
                    data=dict(evento.dados),
                )
                for evento in eventos
            ],
            last_id=log.ultimo_id(),
        )
    except Exception as exc:
        logger.exception("ai_logs failed")
        raise HTTPException(
            status_code=500, detail="Falha ao obter o log da IA"
        ) from exc
