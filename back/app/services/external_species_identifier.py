"""Identificação de aves sob demanda com uma API de visão compatível com a OpenAI.

O provedor é configurável: por padrão usa a OpenAI, mas também aceita qualquer
endpoint compatível com a API de chat da OpenAI (OpenRouter, Groq, Ollama, o
endpoint OpenAI-compatível do Gemini etc.) através de ``AI_EXTERNAL_BASE_URL``.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import requests

from app.core.config import get_settings
from app.core.redaction import redact_secrets

DEFAULT_BASE_URL = "https://api.openai.com/v1"
IDENTIFICATION_PROMPT = (
    "Identifique qual é a espécie desta ave (comum no Brasil) e retorne "
    'o nome científico e popular em formato JSON, usando as chaves '
    '"scientific_name" e "common_name"'
)
# Tamanho máximo da mensagem de erro do provedor exibida ao usuário.
_MAX_DETAIL = 200


class ExternalIdentificationError(RuntimeError):
    """Erro seguro e sem dados sensíveis ao consultar a API externa."""


@dataclass(frozen=True)
class SpeciesIdentification:
    scientific_name: str
    common_name: str


def normalize_base_url(base_url: str | None) -> str:
    """Normaliza e valida a URL base do provedor de IA.

    Aceita apenas ``http``/``https`` com host e remove barras finais (para não
    gerar ``//chat/completions``). Quando vazio, devolve o padrão (OpenAI).
    Levanta ``ValueError`` para URLs inválidas.
    """
    cleaned = (base_url or "").strip().rstrip("/")
    if not cleaned:
        return DEFAULT_BASE_URL
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Informe uma URL base válida (http:// ou https://)")
    return cleaned


def chat_completions_url(base_url: str | None = None) -> str:
    """URL do endpoint de chat completions do provedor configurado."""
    return f"{normalize_base_url(base_url)}/chat/completions"


def provider_error_detail(response: requests.Response) -> str:
    """Extrai a mensagem de erro do provedor, quando disponível."""
    try:
        data = response.json()
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        return error["message"].strip()[:_MAX_DETAIL]
    if isinstance(data.get("message"), str):
        return data["message"].strip()[:_MAX_DETAIL]
    return ""


def _parse_identification(content: str) -> dict[str, object]:
    """Interpreta o conteúdo retornado, tolerando cercas de código Markdown."""
    text = (content or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def _post(
    url: str,
    api_key: str,
    payload: dict[str, object],
) -> requests.Response:
    try:
        return requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=(10, 45),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise ExternalIdentificationError(
            "Não foi possível conectar à API externa de identificação"
        ) from exc


def identify_bird_image(image_bytes: bytes) -> SpeciesIdentification:
    settings = get_settings()
    if not settings.ai_external_api_key:
        raise ExternalIdentificationError(
            "Configure AI_EXTERNAL_API_KEY para habilitar a identificação externa"
        )
    if not image_bytes:
        raise ExternalIdentificationError("O recorte da ave está vazio")

    try:
        url = chat_completions_url(settings.ai_external_base_url)
    except ValueError as exc:
        raise ExternalIdentificationError(str(exc)) from exc

    image_base64 = base64.b64encode(image_bytes).decode("ascii")
    payload: dict[str, object] = {
        "model": settings.ai_external_model,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": IDENTIFICATION_PROMPT},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_base64}",
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
    }

    response = _post(url, settings.ai_external_api_key, payload)
    # Alguns provedores não suportam "response_format"; tenta novamente sem ele.
    if response.status_code == 400 and "response_format" in response.text.lower():
        payload.pop("response_format", None)
        response = _post(url, settings.ai_external_api_key, payload)

    if not 200 <= response.status_code < 300:
        detail = redact_secrets(
            provider_error_detail(response), [settings.ai_external_api_key]
        )
        message = (
            f"A API externa de identificação respondeu com HTTP "
            f"{response.status_code}"
        )
        if detail:
            message = f"{message}: {detail}"
        raise ExternalIdentificationError(message)

    try:
        response_data = response.json()
        content = response_data["choices"][0]["message"]["content"]
        # Alguns provedores devolvem o conteúdo como lista de partes.
        if isinstance(content, list):
            content = "".join(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict)
            )
        identification = _parse_identification(str(content))
        scientific_name = str(identification["scientific_name"]).strip()
        common_name = str(identification["common_name"]).strip()
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        raise ExternalIdentificationError(
            "A API externa retornou uma identificação em formato inválido"
        ) from exc

    if not scientific_name or not common_name:
        raise ExternalIdentificationError(
            "A API externa não retornou os nomes científico e popular"
        )
    return SpeciesIdentification(
        scientific_name=scientific_name,
        common_name=common_name,
    )
