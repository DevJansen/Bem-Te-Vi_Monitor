"""Rotas da Rede Global Bem-Te-Vi Monitor (feed e webhook entre jardins).

O webhook é **opcional** e só aceita eventos quando ``GLOBAL_NETWORK_TOKEN``
está definido. O token deve ser enviado no cabeçalho ``X-Bem-Te-Vi-Token``.
Não há autenticação por query string: segredos em URL vazam em logs e proxies.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException, Query, Request

from app.core.config import get_settings
from app.core.rate_limiter import limiter
from app.domain.models import (
    NetworkFeedOut,
    NetworkStatusOut,
    NetworkWebhookPayload,
    NetworkWebhookResultOut,
)
from app.services.global_network import (
    get_global_network_service,
    token_matches,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/network", tags=["network"])


@router.get("/feed", response_model=NetworkFeedOut)
def get_global_feed(
    days: int | None = Query(default=None, ge=1, le=90),
    limit: int | None = Query(default=None, ge=1, le=100),
) -> NetworkFeedOut:
    """Destaques recentes do jardim e das instâncias parceiras."""
    try:
        payload = get_global_network_service().feed(days=days, limit=limit)
        return NetworkFeedOut(**payload)
    except Exception as exc:
        logger.exception("get_global_feed failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível carregar o Feed Global Bem-Te-Vi.",
        ) from exc


@router.get("/status", response_model=NetworkStatusOut)
def get_global_network_status() -> NetworkStatusOut:
    """Estado da rede (sem expor token, URLs privadas ou credenciais)."""
    try:
        return NetworkStatusOut(**get_global_network_service().status())
    except Exception as exc:
        logger.exception("get_global_network_status failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível consultar o estado da rede global.",
        ) from exc


@router.post("/webhook", response_model=NetworkWebhookResultOut)
@limiter.limit("120/minute")
def receive_global_webhook(
    request: Request,
    payload: NetworkWebhookPayload,
    x_bem_te_vi_token: str | None = Header(
        default=None,
        alias="X-Bem-Te-Vi-Token",
        description="Segredo compartilhado configurado em GLOBAL_NETWORK_TOKEN.",
    ),
) -> NetworkWebhookResultOut:
    """Recebe um destaque de outra instância Bem-Te-Vi (rota opcional)."""
    settings = get_settings()
    if not settings.global_network_enabled:
        raise HTTPException(
            status_code=503,
            detail="A Rede Global Bem-Te-Vi Monitor está desativada nesta instância.",
        )
    if not settings.global_network_token:
        raise HTTPException(
            status_code=503,
            detail=(
                "Webhook desativado: configure GLOBAL_NETWORK_TOKEN para "
                "receber avistamentos de outros jardins."
            ),
        )
    if not token_matches(x_bem_te_vi_token, settings.global_network_token):
        # Não revelamos se o token existe: apenas recusamos.
        raise HTTPException(status_code=401, detail="Token da rede global inválido.")

    try:
        result = get_global_network_service().ingest_peer_event(
            payload.model_dump()
        )
        return NetworkWebhookResultOut(**result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("receive_global_webhook failed")
        raise HTTPException(
            status_code=500,
            detail="Não foi possível registrar o avistamento recebido.",
        ) from exc
