"""Envio de mensagens pelo Telegram (Bot API) com tratamento de falhas.

O Bem-Te-Vi usa este módulo para entregar alertas no Telegram sem nunca
bloquear o pipeline de vídeo: qualquer falha de rede é registrada no log e
convertida em um retorno ``False``, sem propagar exceção para quem chamou.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import requests

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

TELEGRAM_API_BASE = "https://api.telegram.org"
# Limite de caracteres da legenda de mídia imposto pela Bot API.
_MAX_CAPTION = 1024


class TelegramNotifier:
    """Cliente da Bot API do Telegram para o Bem-Te-Vi.

    Métodos são "fire-and-forget": retornam ``True``/``False`` e registram
    erros no log, mas nunca lançam exceção — o pipeline de vídeo não pode
    ser afetado por instabilidade de conexão com a internet.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        timeout: float = 15.0,
        *,
        token: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.timeout = timeout
        # Permite testar credenciais digitadas no painel antes de salvá-las.
        self._token_override = (token or "").strip() or None
        self._chat_id_override = (chat_id or "").strip() or None

    @property
    def token(self) -> str:
        """Token do bot em uso (digitado no teste ou o salvo no .env)."""
        return self._token_override or (self.settings.telegram_bot_token or "").strip()

    @property
    def chat_id(self) -> str:
        """ID do chat em uso (digitado no teste ou o salvo no .env)."""
        return self._chat_id_override or (self.settings.telegram_chat_id or "").strip()

    @property
    def has_token(self) -> bool:
        return bool(self.token)

    @property
    def configured(self) -> bool:
        """Indica se token e chat_id estão presentes."""
        return bool(self.token and self.chat_id)

    @property
    def _api_url(self) -> str:
        return f"{TELEGRAM_API_BASE}/bot{self.token}"

    def send_message(self, text: str) -> bool:
        """Envia uma mensagem de texto. Retorna ``True`` em caso de sucesso."""
        if not self.configured:
            logger.warning("Telegram não configurado — ignorando mensagem")
            return False
        try:
            response = requests.post(
                f"{self._api_url}/sendMessage",
                json={"chat_id": self.chat_id, "text": text},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.error("Falha de conexão ao enviar mensagem Telegram: %s", exc)
            return False

        if response.status_code >= 400:
            logger.error(
                "Telegram recusou a mensagem (HTTP %s): %s",
                response.status_code,
                response.text[:300],
            )
            return False
        return True

    def send_photo(self, photo_path: Path, caption: str) -> bool:
        """Envia uma foto com legenda. Retorna ``True`` em caso de sucesso."""
        if not self.configured:
            logger.warning("Telegram não configurado — ignorando foto")
            return False
        if not photo_path.exists():
            logger.warning("Foto não encontrada para o Telegram: %s", photo_path)
            return False

        try:
            with photo_path.open("rb") as fh:
                response = requests.post(
                    f"{self._api_url}/sendPhoto",
                    data={
                        "chat_id": self.chat_id,
                        "caption": caption[:_MAX_CAPTION],
                    },
                    files={"photo": fh},
                    timeout=self.timeout,
                )
        except requests.RequestException as exc:
            logger.error("Falha de conexão ao enviar foto Telegram: %s", exc)
            return False

        if response.status_code >= 400:
            logger.error(
                "Telegram recusou a foto (HTTP %s): %s",
                response.status_code,
                response.text[:300],
            )
            return False
        return True

    def test_connection(self) -> tuple[bool, str]:
        """Valida o token do bot na Bot API (chamada ``getMe``).

        Retorna ``(ok, detalhe)`` — nunca lança exceção, pois alimenta o
        botão "Testar Envio de Mensagem" do painel.
        """
        if not self.has_token:
            return False, "Informe o token do bot do Telegram"
        try:
            response = requests.get(
                f"{self._api_url}/getMe",
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            return False, f"Sem conexão com a API do Telegram: {exc}"

        if response.status_code >= 400:
            detail = f"Telegram recusou (HTTP {response.status_code}): {response.text[:200]}"
            return False, detail

        name = response.json().get("result", {}).get("username") or "bot"
        return True, f"Conectado como @{name}"


_telegram_notifier: TelegramNotifier | None = None
_notifier_lock = threading.Lock()


def get_telegram_notifier() -> TelegramNotifier:
    """Retorna a instância única do notificador Telegram."""
    global _telegram_notifier
    with _notifier_lock:
        if _telegram_notifier is None:
            _telegram_notifier = TelegramNotifier()
        return _telegram_notifier
