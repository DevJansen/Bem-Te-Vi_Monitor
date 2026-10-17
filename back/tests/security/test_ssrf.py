"""Testes de segurança — validação SSRF de URLs de stream."""

from __future__ import annotations

import pytest

from app.services.url_validator import UrlInvalidaError, validar_url_stream


def test_url_valida_rtsp():
    """URL RTSP válida deve ser aceita."""
    url = "rtsp://8.8.8.8:554/stream"
    assert validar_url_stream(url) == url


def test_url_valida_https():
    """URL HTTPS válida deve ser aceita."""
    url = "https://example.com/stream.m3u8"
    assert validar_url_stream(url) == url


def test_ssrf_localhost():
    """localhost deve ser bloqueado (SSRF)."""
    with pytest.raises(UrlInvalidaError):
        validar_url_stream("http://localhost:8080/admin")


def test_ssrf_loopback():
    """127.0.0.1 deve ser bloqueado (SSRF)."""
    with pytest.raises(UrlInvalidaError):
        validar_url_stream("rtsp://127.0.0.1:554/stream")


def test_ssrf_ip_privado():
    """IPs privados (10.x, 192.168.x) devem ser bloqueados."""
    with pytest.raises(UrlInvalidaError):
        validar_url_stream("http://10.0.0.1:8080/stream")
    with pytest.raises(UrlInvalidaError):
        validar_url_stream("http://192.168.1.1:8080/stream")


def test_ssrf_metadata():
    """Endpoint de metadata (AWS/GCP) deve ser bloqueado."""
    with pytest.raises(UrlInvalidaError):
        validar_url_stream("http://169.254.169.254/latest/meta-data/")


def test_ssrf_protocolo_invalido():
    """Protocolos não permitidos (file://, ftp://) devem ser rejeitados."""
    with pytest.raises(UrlInvalidaError):
        validar_url_stream("file:///etc/passwd")
    with pytest.raises(UrlInvalidaError):
        validar_url_stream("ftp://example.com/file")


def test_ssrf_porta_suspeita():
    """Portas suspeitas (SSH, MySQL, Redis) devem ser bloqueadas."""
    with pytest.raises(UrlInvalidaError):
        validar_url_stream("rtsp://192.168.1.100:22/stream")
    with pytest.raises(UrlInvalidaError):
        validar_url_stream("http://example.com:3306/db")


def test_url_vazia():
    """URL vazia deve ser rejeitada."""
    with pytest.raises(UrlInvalidaError):
        validar_url_stream("")
    with pytest.raises(UrlInvalidaError):
        validar_url_stream(None)  # type: ignore


def test_ssrf_credenciais_http():
    """Credenciais em URL HTTP devem ser rejeitadas."""
    with pytest.raises(UrlInvalidaError):
        validar_url_stream("http://user:pass@example.com/stream")
