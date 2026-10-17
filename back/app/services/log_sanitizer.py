"""Sanitização de logs — filtro customizado para evitar vazamento de segredos.

Garante que senhas, tokens, chaves de API e URLs com credenciais nunca sejam
impressos no console nem salvos em arquivos de log (conformidade LGPD/OWASP).
"""

from __future__ import annotations

import logging
import re
from typing import Any

# Padrões de segredos a serem mascarados.
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Chaves de API (sk-..., AIza..., etc.)
    (re.compile(r"(sk-[A-Za-z0-9_-]{20,})", re.IGNORECASE), "sk-***REDACTED***"),
    (re.compile(r"(AIza[A-Za-z0-9_-]{30,})", re.IGNORECASE), "AIza***REDACTED***"),
    # Senhas em URLs (rtsp://user:pass@host)
    (re.compile(r"(://[^:/\s]+:)[^@\s]+(@)", re.IGNORECASE), r"\1***REDACTED***\2"),
    # Tokens genéricos (Bearer, token=, key=, password=)
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._-]{10,}", re.IGNORECASE), r"\1***REDACTED***"),
    (re.compile(r"(token|api_key|apikey|password|passwd|secret)=([^&\s]{4,})", re.IGNORECASE), r"\1=***REDACTED***"),
    # Chaves Fernet (base64-url de 44 chars)
    (re.compile(r"([A-Za-z0-9_-]{43}=)", re.ASCII), "***FERNET_KEY_REDACTED***"),
]


def sanitizar_texto(texto: str) -> str:
    """Mascara segredos conhecidos em um texto de log."""
    if not texto:
        return texto
    for pattern, replacement in _PATTERNS:
        texto = pattern.sub(replacement, texto)
    return texto


class LogSanitizerFilter(logging.Filter):
    """Filtro de logging que sanitiza mensagens e args antes da emissão."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = sanitizar_texto(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: (sanitizar_texto(v) if isinstance(v, str) else v)
                        for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(
                        sanitizar_texto(a) if isinstance(a, str) else a
                        for a in record.args
                    )
        except Exception:
            pass
        return True


def instalar_sanitizador() -> None:
    """Instala o filtro em todos os handlers do root logger."""
    filtro = LogSanitizerFilter()
    root = logging.getLogger()
    for handler in root.handlers:
        handler.addFilter(filtro)
    # Garante que loggers filhos também propaguem o filtro.
    for logger_name in logging.Logger.manager.loggerDict:
        lg = logging.getLogger(logger_name)
        for handler in lg.handlers:
            handler.addFilter(filtro)
