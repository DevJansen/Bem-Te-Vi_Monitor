"""Rate limiting para rotas sensíveis (OWASP — prevenção de brute force).

Usa ``slowapi`` (wrapper do ``limits``) com armazenamento em memória.
Rotas sensíveis: cadastro de câmeras, teste de IA externa, autenticação.
"""

from __future__ import annotations

import logging
from typing import Callable

from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

# Limiter global baseado no IP do cliente.
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


def rate_limit_exceeded_handler(request, exc):
    """Handler para RateLimitExceeded — retorna 429 com mensagem em pt-BR."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=429,
        content={
            "detail": "Muitas requisições. Tente novamente em alguns instantes."
        },
    )
