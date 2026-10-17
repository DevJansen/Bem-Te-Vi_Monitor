"""Manipulação segura de URLs de stream (redação e extração de credenciais).

Regras de ouro do AviaWatch:

- A URL real (com usuário/senha embutidos) só existe **em memória** no backend.
- Qualquer resposta de API mostra a userInfo mascarada
  (ex.: ``rtsp://****:****@192.168.0.50:554/...``).
- Se o usuário colar um link que **já contenha** credenciais
  (``rtsp://user:senha@host/...``), elas são **extraídas** da URL, criptografadas
  com Fernet e a URL é gravada **sem** a userInfo — nunca em texto plano.
"""

from __future__ import annotations

from urllib.parse import unquote, urlparse, urlunparse


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


def extrair_credenciais_da_url(
    url: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Separa a userInfo embutida em uma URL de stream.

    Retorna ``(url_sem_credenciais, usuario, senha)``. Quando a URL não traz
    credenciais (câmera pública/aberta), devolve a própria URL intacta e
    ``(None, None)`` — permitindo o "colar link e conectar".
    """
    if not url:
        return url, None, None
    texto = str(url).strip()
    try:
        parsed = urlparse(texto)
    except Exception:
        return texto, None, None

    if not parsed.username and not parsed.password:
        return texto, None, None

    usuario = unquote(parsed.username) if parsed.username else None
    senha = unquote(parsed.password) if parsed.password else None

    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    limpa = urlunparse(parsed._replace(netloc=host))
    return limpa, usuario, senha
