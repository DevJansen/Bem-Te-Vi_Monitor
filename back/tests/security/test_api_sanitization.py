"""Testes de segurança — sanitização de respostas de API (no secret leaks)."""

from __future__ import annotations

import os

os.environ.setdefault("ENCRYPTION_KEY", "u7w8X9v2Qp4rT6yU8iO0pA2sD4fG6hJ8kL0zX2cV4bN6mQ8=")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_cameras_list_no_password_leak(client):
    """A listagem de câmeras não deve expor senhas ou URLs brutas."""
    response = client.get("/api/cameras", headers={"Host": "127.0.0.1"})
    # Pode ser 403 (acesso remoto bloqueado) ou 200 — ambos são OK para o teste.
    if response.status_code == 200:
        data = response.json()
        for cam in data:
            assert "password_encrypted" not in cam
            assert "has_credentials" in cam
            # stream_url deve estar redatada (sem credenciais embutidas).
            if "stream_url" in cam:
                assert "@" not in cam["stream_url"] or "REDACTED" in cam["stream_url"]


def test_health_endpoint_no_secrets(client):
    """O endpoint de health não deve expor segredos."""
    response = client.get("/api/health", headers={"Host": "127.0.0.1"})
    assert response.status_code == 200
    body = response.text
    assert "password" not in body.lower()
    assert "token" not in body.lower()
    assert "secret" not in body.lower()


def test_security_headers_present(client):
    """Cabeçalhos de segurança devem estar presentes."""
    response = client.get("/api/health", headers={"Host": "127.0.0.1"})
    headers = response.headers
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert "strict-transport-security" in headers
