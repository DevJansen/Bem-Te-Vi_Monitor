"""Testes de segurança — criptografia Fernet e sanitização de logs."""

from __future__ import annotations

import os

os.environ.setdefault("ENCRYPTION_KEY", "u7w8X9v2Qp4rT6yU8iO0pA2sD4fG6hJ8kL0zX2cV4bN6mQ8=")

from app.infra.camera.crypto import decrypt_secret, encrypt_secret


def test_fernet_roundtrip():
    """Criptografia Fernet deve codificar e decodificar corretamente."""
    plaintext = "senha_super_secreta_123!"
    token = encrypt_secret(plaintext)
    assert token is not None
    assert token != plaintext
    assert decrypt_secret(token) == plaintext


def test_fernet_none_handling():
    """Valores None/vazios devem ser tratados sem erro."""
    assert encrypt_secret(None) is None
    assert encrypt_secret("") is None
    assert decrypt_secret(None) is None
    assert decrypt_secret("") is None


def test_fernet_different_tokens():
    """Cada criptografia deve gerar um token diferente (IV aleatório)."""
    t1 = encrypt_secret("mesma_senha")
    t2 = encrypt_secret("mesma_senha")
    assert t1 != t2
    assert decrypt_secret(t1) == decrypt_secret(t2) == "mesma_senha"


def test_log_sanitizer_redacts_secrets():
    """O sanitizador deve mascarar senhas, tokens e URLs com credenciais."""
    from app.services.log_sanitizer import sanitizar_texto

    texto = "Conectando em rtsp://admin:senha123@192.168.1.10:554/stream"
    resultado = sanitizar_texto(texto)
    assert "senha123" not in resultado
    assert "***REDACTED***" in resultado

    texto2 = "API key: sk-abcdefghijklmnopqrstuvwxyz123456"
    resultado2 = sanitizar_texto(texto2)
    assert "abcdefghijklmnopqrstuvwxyz123456" not in resultado2

    texto3 = "token=meu_token_secreto_12345"
    resultado3 = sanitizar_texto(texto3)
    assert "meu_token_secreto_12345" not in resultado3
