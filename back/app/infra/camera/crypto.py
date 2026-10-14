"""Lightweight local credential encryption (Fernet, key never leaves the machine)."""

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


def _load_or_create_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet

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
