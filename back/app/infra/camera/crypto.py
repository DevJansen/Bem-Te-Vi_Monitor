"""Criptografia local de credenciais (Fernet — chave nunca sai da máquina).

Ordem de obtenção da chave mestra:
1. ``ENCRYPTION_KEY`` do ``.env`` (recomendado em produção — permite rotação e
   backup controlado pela equipe).
2. Chave persistida em ``secrets/camera_key.fernet`` (gerada na 1ª execução).

A URL descriptografada e a senha existem **apenas em memória**, no instante de
abrir o ``VideoCapture`` — nunca são gravadas em log, banco ou resposta de API.
"""

from __future__ import annotations

import logging
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_KEY_FILENAME = "camera_key.fernet"
_fernet: Fernet | None = None


def _key_path() -> Path:
    settings = get_settings()
    settings.ensure_directories()
    return settings.secrets_dir / _KEY_FILENAME


def _fernet_from_key(key: str) -> Fernet | None:
    """Valita uma chave Fernet vinda do ambiente (32 bytes base64-url)."""
    cleaned = (key or "").strip()
    if not cleaned:
        return None
    try:
        return Fernet(cleaned.encode("ascii"))
    except Exception:
        logger.error("ENCRYPTION_KEY inválida — usando chave em arquivo (se existir)")
        return None


def _load_or_create_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

    settings = get_settings()
    # 1) Chave mestra via .env (preferencial).
    if settings.encryption_key:
        _fernet = _fernet_from_key(settings.encryption_key)
        if _fernet is not None:
            return _fernet

    # 2) Chave persistida localmente (fallback).
    path = _key_path()
    try:
        if path.exists():
            key = path.read_bytes().strip()
        else:
            key = Fernet.generate_key()
            path.write_bytes(key)
            try:
                path.chmod(0o600)
            except Exception:
                pass
        _fernet = Fernet(key)
        return _fernet
    except Exception:
        logger.exception("Failed to initialize credential encryption key")
        raise


def encrypt_secret(plaintext: str | None) -> str | None:
    if plaintext is None or plaintext == "":
        return None
    try:
        token = _load_or_create_fernet().encrypt(plaintext.encode("utf-8"))
        return token.decode("ascii")
    except Exception:
        logger.exception("Failed to encrypt secret")
        raise


def decrypt_secret(token: str | None) -> str | None:
    if token is None or token == "":
        return None
    try:
        return _load_or_create_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.error("Invalid credential token — key may have been rotated")
        return None
    except Exception:
        logger.exception("Failed to decrypt secret")
        return None
