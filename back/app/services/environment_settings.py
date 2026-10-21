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
from app.core.redaction import is_masked, mask_secret, mask_url_secret
from app.domain.models import (
    EnvironmentConnectionTest,
    EnvironmentSettingsOut,
    EnvironmentSettingsUpdate,
    NotificationTestResponse,
)
from app.services.ai_service import (
    GEMINI_DEFAULT_MODEL,
    sanitize_model_name,
    test_gemini_connection,
)
from app.services.notification_service import get_notification_service
from app.services.notifier import TelegramNotifier

logger = logging.getLogger(__name__)
_env_lock = threading.RLock()

# Nome canônico da chave do Google Gemini (documentado no .env.example e no
# painel). `AI_EXTERNAL_API_KEY` é o nome legado, mantido apenas como fallback
# para não quebrar instalações antigas.
GEMINI_ENV_KEY = "GEMINI_API_KEY"
AI_LEGACY_ENV_KEY = "AI_EXTERNAL_API_KEY"

_ENV_KEYS = {
    "telegram_bot_token": "TELEGRAM_BOT_TOKEN",
    "telegram_chat_id": "TELEGRAM_CHAT_ID",
    "discord_webhook_url": "DISCORD_WEBHOOK_URL",
    # Toda gravação passa a usar o nome canônico.
    "ai_external_api_key": GEMINI_ENV_KEY,
    "ai_external_model": "AI_EXTERNAL_MODEL",
}


def gemini_key_from(values: dict[str, str]) -> str:
    """Devolve a chave do Gemini configurada, aceitando o nome legado.

    Precedência: ``GEMINI_API_KEY`` → ``AI_EXTERNAL_API_KEY``. A mesma regra é
    usada em ``app/core/config.py``, garantindo que painel, testes de conexão e
    chamadas reais enxerguem sempre a mesma chave.
    """
    return (
        (values.get(GEMINI_ENV_KEY) or "").strip()
        or (values.get(AI_LEGACY_ENV_KEY) or "").strip()
    )


def _read_env_file() -> dict[str, str]:
    if not ENV_FILE.is_file():
        return {}
    parsed = dotenv_values(ENV_FILE)
    return {key: value for key, value in parsed.items() if value is not None}


def _masked_display(field_name: str, value: str | None) -> str | None:
    """Mascaramento conforme o tipo do campo (URL de webhook x segredo comum)."""
    if field_name == "discord_webhook_url":
        return mask_url_secret(value)
    return mask_secret(value)


def _is_unchanged_mask(
    field_name: str,
    env_name: str,
    cleaned: str,
    current: dict[str, str],
) -> bool:
    """Detecta quando o valor enviado é apenas a máscara (sem alteração real).

    Evita que o usuário, ao salvar o formulário com o campo mascarado visível,
    grave literalmente ``AIza...****`` por cima do segredo verdadeiro.
    """
    if is_masked(cleaned):
        return True
    stored = current.get(env_name)
    if env_name == GEMINI_ENV_KEY:
        # A chave pode estar salva com o nome legado; compara com a resolvida.
        stored = gemini_key_from(current)
    if not stored:
        return False
    return cleaned == _masked_display(field_name, stored)


def read_environment_settings() -> EnvironmentSettingsOut:
    values = _read_env_file()
    ai_key = gemini_key_from(values)
    telegram_configured = bool(
        values.get("TELEGRAM_BOT_TOKEN") and values.get("TELEGRAM_CHAT_ID")
    )
    discord_configured = bool(values.get("DISCORD_WEBHOOK_URL"))
    ai_external_configured = bool(ai_key)
    return EnvironmentSettingsOut(
        telegram_bot_token=mask_secret(values.get("TELEGRAM_BOT_TOKEN")),
        telegram_chat_id=mask_secret(values.get("TELEGRAM_CHAT_ID")),
        discord_webhook_url=mask_url_secret(values.get("DISCORD_WEBHOOK_URL")),
        ai_external_api_key=mask_secret(ai_key),
        ai_external_model=(
            sanitize_model_name(values.get("AI_EXTERNAL_MODEL"))
            or GEMINI_DEFAULT_MODEL
        ),
        telegram_bot_token_configured=bool(values.get("TELEGRAM_BOT_TOKEN")),
        telegram_chat_id_configured=bool(values.get("TELEGRAM_CHAT_ID")),
        discord_webhook_url_configured=bool(values.get("DISCORD_WEBHOOK_URL")),
        ai_external_api_key_configured=bool(ai_key),
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
    current_values = _read_env_file()
    for field_name, env_name in _ENV_KEYS.items():
        value = getattr(payload, field_name)
        if field_name in supplied and value is not None:
            cleaned = value.strip()
            # Reenvio do valor mascarado (sem alteração) é ignorado.
            if _is_unchanged_mask(field_name, env_name, cleaned, current_values):
                continue
            if "\n" in cleaned or "\r" in cleaned or "\x00" in cleaned:
                raise ValueError(f"Valor inválido para {env_name}")
            # O Google Gemini é o único provedor: normalizamos o nome do modelo
            # removendo prefixos inválidos (ex.: "models/gemini-3.5-flash"),
            # que causariam HTTP 404 na API oficial.
            if field_name == "ai_external_model":
                cleaned = sanitize_model_name(cleaned)
            values_to_save[env_name] = cleaned

    clear_by_integration = {
        "clear_telegram": ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"),
        "clear_discord": ("DISCORD_WEBHOOK_URL",),
        # Limpa o nome canônico e o legado, para não sobrar chave "fantasma".
        "clear_ai_external": (GEMINI_ENV_KEY, AI_LEGACY_ENV_KEY),
    }
    cleared_keys = {
        env_name
        for field_name, env_names in clear_by_integration.items()
        if getattr(payload, field_name)
        for env_name in env_names
    }
    if GEMINI_ENV_KEY in values_to_save:
        # Ao gravar a chave canônica, descarta a cópia legada (se existir):
        # duas chaves diferentes no .env confundem o usuário e os testes.
        cleared_keys.add(AI_LEGACY_ENV_KEY)
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
    json: dict[str, object] | None = None,
) -> requests.Response:
    try:
        return requests.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json,
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

        # Testa com as credenciais digitadas no painel (ou as salvas, se vazias).
        telegram = TelegramNotifier(token=token, chat_id=chat_id)
        ok, detail = telegram.test_connection()
        if not ok:
            raise RuntimeError(detail)

        if not chat_id:
            # Sem chat não há para quem enviar; valida apenas o token.
            return NotificationTestResponse(
                ok=True,
                message=f"Conexão com o Telegram validada. {detail}",
            )

        if not telegram.send_message(
            "Bem-Te-Vi — teste de alerta.\n"
            "Se você recebeu esta mensagem, os alertas estão funcionando!"
        ):
            raise RuntimeError(
                "O Telegram validou o bot, mas não aceitou a mensagem de teste. "
                "Verifique o ID do chat e se o bot foi iniciado por você."
            )
        return NotificationTestResponse(
            ok=True,
            message=f"Mensagem de teste enviada com sucesso. {detail}",
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

    # =================== IA EXTERNA (Google Gemini) ====================== #
    api_key = payload.ai_external_api_key or gemini_key_from(current)
    if not api_key:
        raise ValueError("Informe a chave da API do Google Gemini para testar")
    # O nome do modelo é sanitizado (remove "models/") para evitar HTTP 404.
    model = sanitize_model_name(
        payload.ai_external_model
        or current.get("AI_EXTERNAL_MODEL", "")
        or GEMINI_DEFAULT_MODEL
    )

    # Teste blindado: prompt leve, backoff exponencial (3 tentativas) e
    # fallback automático no gemini-2.5-flash quando o modelo devolve 404.
    ok, message = test_gemini_connection(api_key, model)
    if not ok:
        raise RuntimeError(message)
    return NotificationTestResponse(ok=True, message=message)
