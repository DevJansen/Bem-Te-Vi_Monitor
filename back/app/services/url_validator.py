"""Validação de URLs de stream — prevenção de SSRF (OWASP).

Garante que URLs de câmeras inseridas pelo usuário não apontem para recursos
internos (localhost, IPs privados, file://, etc.), bloqueando tentativas de
varredura de portas ou acesso a serviços internos.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Protocolos permitidos para streams de câmeras.
_PROTOCOLOS_PERMITIDOS = {"rtsp", "rtsps", "http", "https", "hls"}

# Hosts/IPs bloqueados (SSRF).
_HOSTS_BLOQUEADOS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "169.254.169.254",  # AWS/GCP metadata
}


class UrlInvalidaError(ValueError):
    """Levantada quando a URL não passa na validação SSRF."""


def _eh_ip_privado(host: str) -> bool:
    """Indica se o host é um IP privado/reservado (RFC 1918, loopback, etc.)."""
    try:
        ip = ipaddress.ip_address(host)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        )
    except ValueError:
        return False


def validar_url_stream(url: str) -> str:
    """Valida uma URL de stream contra SSRF.

    Retorna a URL normalizada se válida, levanta UrlInvalidaError caso contrário.
    """
    if not url or not isinstance(url, str):
        raise UrlInvalidaError("URL vazia ou inválida.")

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception:
        raise UrlInvalidaError("URL malformada.")

    if not parsed.scheme or not parsed.hostname:
        raise UrlInvalidaError("URL deve ter protocolo e host.")

    scheme = parsed.scheme.lower()
    if scheme not in _PROTOCOLOS_PERMITIDOS:
        raise UrlInvalidaError(
            f"Protocolo '{scheme}' não permitido. Use rtsp, rtsps, http, https ou hls."
        )

    host = parsed.hostname.lower()
    if host in _HOSTS_BLOQUEADOS:
        raise UrlInvalidaError(f"Host '{host}' bloqueado (SSRF).")

    if _eh_ip_privado(host):
        raise UrlInvalidaError(f"IP privado/reservado '{host}' bloqueado (SSRF).")

    # Bloqueia portas suspeitas (ex.: 22 SSH, 3306 MySQL, 6379 Redis).
    porta = parsed.port
    if porta is not None and porta in {22, 23, 25, 3306, 5432, 6379, 27017, 11211}:
        raise UrlInvalidaError(f"Porta {porta} bloqueada por segurança.")

    # Bloqueia userinfo com credenciais em URLs HTTP (devem ir via campos separados).
    if parsed.username or parsed.password:
        if scheme in {"http", "https"}:
            raise UrlInvalidaError(
                "Credenciais em URL HTTP não permitidas; use os campos de usuário/senha."
            )

    return url
