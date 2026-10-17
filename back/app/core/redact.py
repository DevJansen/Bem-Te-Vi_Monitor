"""Redação de URLs de stream para nunca expor credenciais no front-end.

A URL real (com usuário/senha embutidos) só existe em memória no backend. Qualquer
resposta de API ou exibição mostra apenas o host/porta, com a userInfo mascarada
(ex.: ``rtsp://****:****@192.168.0.50:554/...``).
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse


def redact_url(url: str | None) -> str | None:
    """Devolve a URL com a userInfo (usuário/senha) mascarada.

    Se não houver credenciais ou a URL for inválida, devolve o valor original.
    """
    if not url:
        return url
    try:
        parsed = urlparse(str(url))
    except Exception:
        return str(url)
    tem_credencial = bool(parsed.username) or bool(parsed.password)
    if not tem_credencial:
        return str(url)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    mascarado = f"****:****@{host}"
    return urlunparse(parsed._replace(netloc=mascarado))
