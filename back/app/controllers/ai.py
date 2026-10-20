"""Rotas REST do motor de IA (AI Core).

Expõe o "coração pulsante" do Bem-Te-Vi: o estado do modelo, a telemetria de
desempenho (FPS, latência, inferências) e o **log cognitivo** — os "pensamentos"
da IA em tempo real, consumidos pelo painel futurista do Dashboard.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.ai.active_learning import (
    ActiveLearningError,
    get_active_learning_service,
)
from app.ai.behavioral_memory import get_behavioral_memory_service
from app.ai.visual_embeddings import get_visual_embeddings_service
from app.core.branding import ALARIS_SIGNATURE
from app.core.config import get_settings
from app.domain.models import (
    ActiveLearningStatusOut,
    AiEngineOut,
    AiLogOut,
    AiLogsOut,
    AiPerformanceOut,
    AiResourcesOut,
    AiStatusOut,
    AiThroughputOut,
    BehavioralMemoryStatusOut,
    BehavioralPredictionListOut,
    KnownIndividualDetailOut,
    KnownIndividualListOut,
    KnownIndividualOut,
    VisualEmbeddingsStatusOut,
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
            cameras_enabled = sum(1 for row in repo.list_all() if row["is_active"])
            status_map = get_camera_manager().status_map()
            cameras_online = sum(
                1 for status in status_map.values() if status == "online"
            )
        except Exception:
            logger.debug("Falha ao contar câmeras", exc_info=True)

        return AiStatusOut(
            signature=ALARIS_SIGNATURE,
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


# --------------------------------------------------------------------------- #
# Inteligência adaptativa
# --------------------------------------------------------------------------- #


@router.get("/learning/status", response_model=ActiveLearningStatusOut)
def ai_learning_status() -> ActiveLearningStatusOut:
    """Fila de amostras e histórico de fine-tuning do Bem-Ti-Vi Core."""
    try:
        status = get_active_learning_service().status()
        return ActiveLearningStatusOut(**status)
    except Exception as exc:
        logger.exception("ai_learning_status failed")
        raise HTTPException(
            status_code=500,
            detail="Falha ao obter o status do aprendizado ativo",
        ) from exc


@router.post("/learning/optimize", response_model=ActiveLearningStatusOut)
def ai_learning_optimize() -> ActiveLearningStatusOut:
    """Dispara o fine-tuning incremental ("Otimizar Bem-Ti-Vi Core")."""
    try:
        status = get_active_learning_service().start_fine_tuning()
        return ActiveLearningStatusOut(**status)
    except ActiveLearningError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("ai_learning_optimize failed")
        raise HTTPException(
            status_code=500,
            detail="Falha ao iniciar a otimização do Bem-Ti-Vi Core",
        ) from exc


@router.get("/behavioral-prediction", response_model=BehavioralPredictionListOut)
def ai_behavioral_prediction(
    species: str | None = Query(
        default=None,
        description="Restringe a previsão a uma espécie (nome popular).",
    ),
    horizon_hours: int | None = Query(
        default=None,
        ge=1,
        le=12,
        description="Janela de previsão em horas (padrão das configurações).",
    ),
    limit: int = Query(default=8, ge=1, le=24),
) -> BehavioralPredictionListOut:
    """Prevê picos de atividade cruzando histórico, clima e sazonalidade."""
    try:
        payload = get_behavioral_memory_service().predict(
            species=species,
            horizon_hours=horizon_hours,
            limit=limit,
        )
        return BehavioralPredictionListOut(**payload)
    except Exception as exc:
        logger.exception("ai_behavioral_prediction failed")
        raise HTTPException(
            status_code=500, detail="Falha ao calcular a previsão comportamental"
        ) from exc


@router.get("/behavioral-memory", response_model=BehavioralMemoryStatusOut)
def ai_behavioral_memory() -> BehavioralMemoryStatusOut:
    """Resumo da memória comportamental persistida."""
    try:
        return BehavioralMemoryStatusOut(
            **get_behavioral_memory_service().status()
        )
    except Exception as exc:
        logger.exception("ai_behavioral_memory failed")
        raise HTTPException(
            status_code=500, detail="Falha ao obter a memória comportamental"
        ) from exc


@router.post("/behavioral-memory/refresh", response_model=BehavioralMemoryStatusOut)
def ai_behavioral_memory_refresh() -> BehavioralMemoryStatusOut:
    """Força a reconstrução dos perfis comportamentais agora."""
    try:
        service = get_behavioral_memory_service()
        service.refresh()
        return BehavioralMemoryStatusOut(**service.status())
    except Exception as exc:
        logger.exception("ai_behavioral_memory_refresh failed")
        raise HTTPException(
            status_code=500,
            detail="Falha ao atualizar a memória comportamental",
        ) from exc


@router.get("/individuals", response_model=KnownIndividualListOut)
def ai_individuals(
    species_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> KnownIndividualListOut:
    """Lista os "Conhecidos do Jardim" reconhecidos por assinatura visual."""
    try:
        individuals = get_visual_embeddings_service().list_individuals(
            species_id=species_id, limit=limit
        )
        return KnownIndividualListOut(
            individuals=[KnownIndividualOut(**item) for item in individuals],
            total=len(individuals),
        )
    except Exception as exc:
        logger.exception("ai_individuals failed")
        raise HTTPException(
            status_code=500, detail="Falha ao listar os indivíduos conhecidos"
        ) from exc


@router.get("/individuals/{individual_id}", response_model=KnownIndividualDetailOut)
def ai_individual_detail(individual_id: str) -> KnownIndividualDetailOut:
    """Histórico completo de um indivíduo ("Conhecido do Jardim")."""
    try:
        payload = get_visual_embeddings_service().individual_history(individual_id)
    except Exception as exc:
        logger.exception("ai_individual_detail failed")
        raise HTTPException(
            status_code=500, detail="Falha ao obter o histórico do indivíduo"
        ) from exc
    if payload is None:
        raise HTTPException(status_code=404, detail="Indivíduo não encontrado")
    return KnownIndividualDetailOut(**payload)


@router.get("/visual/status", response_model=VisualEmbeddingsStatusOut)
def ai_visual_status() -> VisualEmbeddingsStatusOut:
    """Contadores das assinaturas visuais (re-identificação individual)."""
    try:
        return VisualEmbeddingsStatusOut(**get_visual_embeddings_service().status())
    except Exception as exc:
        logger.exception("ai_visual_status failed")
        raise HTTPException(
            status_code=500,
            detail="Falha ao obter o status das assinaturas visuais",
        ) from exc
