"""Identificação de aves sob demanda com a API de visão da OpenAI."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass

import requests

from app.core.config import get_settings

OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
IDENTIFICATION_PROMPT = (
    "Identifique qual é a espécie desta ave (comum no Brasil) e retorne "
    'o nome científico e popular em formato JSON, usando as chaves '
    '"scientific_name" e "common_name"'
)


class ExternalIdentificationError(RuntimeError):
    """Erro seguro e sem dados sensíveis ao consultar a API externa."""


@dataclass(frozen=True)
class SpeciesIdentification:
    scientific_name: str
    common_name: str


def identify_bird_image(image_bytes: bytes) -> SpeciesIdentification:
    settings = get_settings()
    if not settings.ai_external_api_key:
        raise ExternalIdentificationError(
            "Configure AI_EXTERNAL_API_KEY para habilitar a identificação externa"
        )
    if not image_bytes:
        raise ExternalIdentificationError("O recorte da ave está vazio")

    image_base64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
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
    try:
        response = requests.post(
            OPENAI_CHAT_COMPLETIONS_URL,
            headers={"Authorization": f"Bearer {settings.ai_external_api_key}"},
            json=payload,
            timeout=(10, 45),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise ExternalIdentificationError(
            "Não foi possível conectar à API externa de identificação"
        ) from exc

    if not 200 <= response.status_code < 300:
        raise ExternalIdentificationError(
            f"A API externa de identificação respondeu com HTTP {response.status_code}"
        )

    try:
        response_data = response.json()
        content = response_data["choices"][0]["message"]["content"]
        identification = json.loads(content)
        scientific_name = identification["scientific_name"].strip()
        common_name = identification["common_name"].strip()
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
