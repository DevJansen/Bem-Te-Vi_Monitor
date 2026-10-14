"""Leitura mascarada, gravação segura e testes das integrações do arquivo .env."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from pathlib import Path

import requests
from dotenv import dotenv_values, load_dotenv, set_key, unset_key

from app.core.config import ENV_FILE, get_settings
from app.domain.models import (
    EnvironmentConnectionTest,
    EnvironmentSettingsOut,
    EnvironmentSettingsUpdate,
    NotificationTestResponse,
)
from app.services.notification_service import get_notification_service

logger = logging.getLogger(__name__)
_env_lock = threading.RLock()
_ENV_KEYS = {
    "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
    "telegram_chat_id": "TELEGRAM_CHAT_ID",
    "discord_webhook_url": "DISCORD_WEBHOOK_URL",
    "ai_external_api_key": "AI_EXTERNAL_API_KEY",
}
_MASK = "********"


def _read_env_file() -> dict[str, str]:
    if not ENV_FILE.is_file():
        return {}
    parsed = dotenv_values(ENV_FILE)
    return {key: value for key, value in parsed.items() if value is not None}


def _masked(value: str | None) -> str | None:
    return _MASK if value else None


def read_environment_settings() -> EnvironmentSettingsOut:
    values = _read_env_file()
    telegram_configured = bool(
        values.get("TELEGRAM_BOT_TOKEN") and values.get("TELEGRAM_CHAT_ID")
    )
    discord_configured = bool(values.get("DISCORD_WEBHOOK_URL"))
    ai_external_configured = bool(values.get("AI_EXTERNAL_API_KEY"))
    return EnvironmentSettingsOut(
        telegram_bot_token=_masked(values.get("TELEGRAM_BOT_TOKEN")),
        telegram_chat_id=_masked(values.get("TELEGRAM_CHAT_ID")),
        discord_webhook_url=_masked(values.get("DISCORD_WEBHOOK_URL")),
        ai_external_api_key=_masked(values.get("AI_EXTERNAL_API_KEY")),
        telegram_bot_token_configured=bool(values.get("TELEGRAM_BOT_TOKEN")),
        telegram_chat_id_configured=bool(values.get("TELEGRAM_CHAT_ID")),
        discord_webhook_url_configured=bool(values.get("DISCORD_WEBHOOK_URL")),
        ai_external_api_key_configured=bool(values.get("AI_EXTERNAL_API_KEY")),
        telegram_configured=telegram_configured,
        discord_configured=discord_configured,
        ai_external_configured=ai_external_configured,
    )


def _refresh_runtime_environment(cleared_keys: set[str]) -> None:
    load_dotenv(dotenv_path=ENV_FILE, override=True)
    for key in cleared_keys:
        os.environ.pop(key, None)
    get_settings.cache_clear()
    current_settings = get_settings()
    get_notification_service().settings = current_settings


def save_environment_settings(
    payload: EnvironmentSettingsUpdate,
) -> EnvironmentSettingsOut:
    supplied = payload.model_fields_set
    values_to_save: dict[str, str] = {}
    for field_name, env_name in _ENV_KEYS.items():
        value = getattr(payload, field_name)
        if field_name in supplied and value is not None:
            cleaned = value.strip()
            if cleaned == _MASK:
                continue
            if "\n" in cleaned or "\r" in cleaned or "\x00" in cleaned:
                raise ValueError(f"Valor inválido para {env_name}")
            values_to_save[env_name] = cleaned

    clear_by_integration = {
        "clear_telegram": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"),
        "clear_discord": ("DISCORD_WEBHOOK_URL",),
        "clear_ai_external": ("AI_EXTERNAL_API_KEY",),
    }
    cleared_keys = {
        env_name
        for field_name, env_names in clear_by_integration.items()
        if getattr(payload, field_name)
        for env_name in env_names
    }
    for env_name in cleared_keys:
        values_to_save.pop(env_name, None)

    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    with _env_lock:
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".env-",
                suffix=".tmp",
                dir=ENV_FILE.parent,
                text=True,
            )
            os.close(descriptor)
            temporary_path = Path(temporary_name)
            if ENV_FILE.is_file():
                temporary_path.write_text(
                    ENV_FILE.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
            for env_name, value in values_to_save.items():
                set_key(
                    str(temporary_path),
                    env_name,
                    value,
                    quote_mode="always",
                    export=False,
                )
            for env_name in cleared_keys:
                unset_key(str(temporary_path), env_name)
            try:
                os.chmod(temporary_path, 0o600)
            except OSError:
                logger.warning("Could not restrict .env file permissions on this OS")
            os.replace(temporary_path, ENV_FILE)
            temporary_path = None
        except Exception:
            logger.exception("Failed to save environment configuration")
            raise
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
        _refresh_runtime_environment(cleared_keys)

    return read_environment_settings()


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> requests.Response:
    try:
        return requests.request(
            method,
            url,
            headers=headers,
            params=params,
            timeout=(5, 12),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise RuntimeError("Não foi possível conectar ao serviço externo") from exc


def test_environment_connection(
    payload: EnvironmentConnectionTest,
) -> NotificationTestResponse:
    current = _read_env_file()

    if payload.integration == "telegram":
        token = payload.telegram_bot_token or current.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = payload.telegram_chat_id or current.get("TELEGRAM_CHAT_ID", "")
        if not token:
            raise ValueError("Informe o token do bot do Telegram para testar")
        response = _request(
            "GET",
            f"https://api.telegram.org/bot{token}/getMe",
        )
        if response.status_code != 200:
            raise RuntimeError("O Telegram rejeitou o token informado")
        try:
            if not response.json().get("ok"):
                raise RuntimeError("O Telegram rejeitou o token informado")
        except (ValueError, AttributeError) as exc:
            raise RuntimeError("Resposta inválida do Telegram") from exc
        if chat_id:
            chat_response = _request(
                "GET",
                f"https://api.telegram.org/bot{token}/getChat",
                params={"chat_id": chat_id},
            )
            if chat_response.status_code != 200:
                raise RuntimeError("O Telegram não reconheceu o chat informado")
        return NotificationTestResponse(
            ok=True,
            message="Conexão com o Telegram validada.",
        )

    if payload.integration == "discord":
        webhook = payload.discord_webhook_url or current.get("DISCORD_WEBHOOK_URL", "")
        if not webhook:
            raise ValueError("Informe a URL do webhook do Discord para testar")
        from urllib.parse import urlparse

        parsed = urlparse(webhook)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"discord.com", "discordapp.com"}
            or not parsed.path.startswith("/api/webhooks/")
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Informe uma URL HTTPS válida de webhook do Discord")
        response = _request("GET", webhook)
        if response.status_code != 200:
            raise RuntimeError("O Discord rejeitou o webhook informado")
        return NotificationTestResponse(
            ok=True,
            message="Conexão com o webhook do Discord validada.",
        )

    api_key = payload.ai_external_api_key or current.get("AI_EXTERNAL_API_KEY", "")
    if not api_key:
        raise ValueError("Informe a chave da IA Externa para testar")
    response = _request(
        "GET",
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    if response.status_code != 200:
        raise RuntimeError("A API de IA Externa rejeitou a chave informada")
    return NotificationTestResponse(
        ok=True,
        message="Conexão com a API de IA Externa validada.",
    )
