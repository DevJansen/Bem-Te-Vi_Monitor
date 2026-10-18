"""Middlewares de segurança da API (ASGI puro).

Implementados como ASGI puro — e não com ``BaseHTTPMiddleware`` — para não
interferir em respostas de streaming (o MJPEG de ``/api/video-feed`` mantém a
conexão aberta e não pode ser "bufferizado" por um wrapper).

- :class:`SecurityHeadersMiddleware` injeta cabeçalhos de segurança HTTP.
- :class:`LocalAccessGuardMiddleware` bloqueia conexões que não venham do
  próprio computador (loopback), a menos que o acesso remoto seja liberado
  explicitamente por ``ALLOW_REMOTE_ACCESS=true``.
"""

from __future__ import annotations

import ipaddress
import json
import logging
from typing import Any, Callable, MutableMapping

logger = logging.getLogger(__name__)

# Cabeçalhos aplicados a TODA resposta HTTP da API.
SECURITY_HEADERS: dict[str, str] = {
    # HSTS: força HTTPS por 1 ano (em produção com TLS).
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    # Impede que o navegador "adivinhe" o tipo de conteúdo (evita XSS por sniffing).
    "X-Content-Type-Options": "nosniff",
    # Impede o carregamento da API dentro de iframes (anti-clickjacking).
    "X-Frame-Options": "DENY",
    # Não vaza a URL de origem em requisições externas.
    "Referrer-Policy": "no-referrer",
    # Desliga recursos sensíveis que o painel não utiliza.
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    # same-site (e não same-origin) para não quebrar mídia servida em outra porta
    # do mesmo host durante o desenvolvimento.
    "Cross-Origin-Resource-Policy": "same-site",
    "X-Permitted-Cross-Domain-Policies": "none",
    # CSP compatível com a UI do Swagger (/docs) e com a mídia local.
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' data: blob:; "
        "media-src 'self' blob:; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    ),
}

# Caminhos liberados mesmo fora do loopback (verificação de saúde e raiz).
_PUBLIC_PATHS = {"/", "/health", "/api/health"}

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]


def _is_loopback(host: str) -> bool:
    """Indica se o host da conexão é local (127.0.0.0/8, ::1 ou localhost)."""
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


class SecurityHeadersMiddleware:
    """Adiciona cabeçalhos de segurança a todas as respostas HTTP."""

    def __init__(self, app: Callable, headers: dict[str, str] | None = None) -> None:
        self.app = app
        self.headers = headers or SECURITY_HEADERS

    async def __call__(
        self, scope: Scope, receive: Callable, send: Callable
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                raw: list[tuple[bytes, bytes]] = list(message.get("headers") or [])
                present = {key.lower() for key, _ in raw}
                for name, value in self.headers.items():
                    key = name.lower().encode("latin-1")
                    if key not in present:
                        raw.append((key, value.encode("latin-1")))
                message["headers"] = raw
            await send(message)

        await self.app(scope, receive, send_with_headers)


class LocalAccessGuardMiddleware:
    """Restringe a API a conexões locais, salvo liberação explícita.

    Padrão seguro do Bem-Te-Vi: a API responde apenas ao próprio computador.
    Se o servidor for exposto na rede (ex.: ``HOST=0.0.0.0``) sem definir
    ``ALLOW_REMOTE_ACCESS=true``, toda origem externa recebe ``403``.
    """

    def __init__(self, app: Callable, *, allow_remote: bool = False) -> None:
        self.app = app
        self.allow_remote = allow_remote

    async def __call__(
        self, scope: Scope, receive: Callable, send: Callable
    ) -> None:
        if scope["type"] != "http" or self.allow_remote:
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        client = scope.get("client") or ("", 0)
        client_host = client[0] if client else ""

        if path in _PUBLIC_PATHS or _is_loopback(client_host):
            await self.app(scope, receive, send)
            return

        logger.warning(
            "Requisição remota bloqueada (acesso remoto desativado): %s %s de %s",
            scope.get("method"),
            path,
            client_host or "desconhecido",
        )
        body = json.dumps(
            {"detail": "Acesso remoto desativado. Utilize o painel no computador local."}
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
