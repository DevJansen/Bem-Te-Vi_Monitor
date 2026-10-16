"""Mascaramento estrito de segredos.

Nenhuma chave, token ou credencial deve aparecer por inteiro em logs, respostas
de API ou mensagens de erro. Este módulo centraliza a regra de exibição segura:

- :func:`mask_secret` mostra apenas os primeiros caracteres e oculta o resto
  (ex.: ``AIza...****``). Segredos curtos são totalmente ocultados.
- :func:`mask_url_secret` mascara a parte sensível de uma URL (ex.: webhook do
  Discord), preservando apenas o esquema e o host para o usuário se orientar.
"""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlparse

# Marcador fixo do trecho oculto. É reconhecido em `environment_settings` para
# detectar quando o usuário apenas reenviou o valor mascarado (sem alteração).
MASK_SUFFIX = "...****"
_FALLBACK_MASK = "********"


def mask_secret(value: str | None, *, visible: int = 4) -> str | None:
    """Devolve a versão mascarada de um segredo (ou ``None`` se vazio).

    Exibe no máximo ``visible`` caracteres iniciais seguidos de um marcador fixo,
    o suficiente para o usuário reconhecer a chave sem expô-la. Valores curtos
    (menores ou iguais a ``visible``) são ocultados por completo.
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) <= visible:
        return _FALLBACK_MASK
    return f"{text[:visible]}{MASK_SUFFIX}"


def mask_url_secret(url: str | None) -> str | None:
    """Mascara a parte sensível de uma URL, mantendo apenas esquema e host.

    Ex.: ``https://discord.com/api/webhooks/123/abc`` -> ``https://discord.com/...****``.
    URLs inválidas caem no mascaramento genérico de :func:`mask_secret`.
    """
    if not url:
        return None
    text = url.strip()
    if not text:
        return None
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.hostname:
        return mask_secret(text)
    return f"{parsed.scheme}://{parsed.hostname}{MASK_SUFFIX}"


def is_masked(value: str | None) -> bool:
    """Indica se o texto recebido é um valor mascarado (e não um segredo real)."""
    if not value:
        return False
    text = value.strip()
    return text == _FALLBACK_MASK or text.endswith(MASK_SUFFIX)


def redact_secrets(text: str | None, secrets: Iterable[str | None]) -> str:
    """Remove segredos conhecidos de um texto (ex.: mensagem de erro do provedor).

    Alguns provedores ecoam a chave recebida na mensagem de erro; esta função
    substitui qualquer ocorrência exata pelo valor mascarado antes de exibir.
    """
    if not text:
        return ""
    redacted = text
    for secret in secrets:
        if secret and len(secret) >= 6:
            redacted = redacted.replace(secret, mask_secret(secret) or "")
    return redacted
