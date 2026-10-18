"""Identificação de aves sob demanda com APIs de visão externas.

Dois modos de provedor:

- **Google Gemini (oficial):** usa o endpoint REST do Google Generative
  Language (``.../v1beta/models/{modelo}:generateContent``) com a chave na
  *query string* (``?key=``). É o modo correto para o Gemini e evita o **HTTP
  404** que acontece ao mandar a chave/modelo para uma rota padrão da OpenAI.
- **Compatível com a OpenAI:** OpenAI, OpenRouter, Groq, Ollama e qualquer
  endpoint de chat da OpenAI, configurado por ``AI_EXTERNAL_BASE_URL`` (o chat é
  chamado em ``{base}/chat/completions``).

O provedor efetivo é resolvido por :func:`detect_provider`, que aceita tanto o
campo ``AI_EXTERNAL_PROVIDER`` quanto a própria URL base — mantendo a
compatibilidade com configurações antigas que só guardavam a URL.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from app.core.config import get_settings
from app.core.redaction import redact_secrets

# --- Provedores ---------------------------------------------------------- #
PROVIDER_GOOGLE = "google"
PROVIDER_OPENAI = "openai"

# URL base e modelo padrão do endpoint oficial do Google Gemini.
GOOGLE_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GOOGLE_DEFAULT_MODEL = "gemini-2.5-flash"
GOOGLE_API_VERSION = "v1beta"

# URL base e modelo padrão do provedor compatível com a OpenAI.
DEFAULT_BASE_URL = "https://api.openai.com/v1"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"

IDENTIFICATION_PROMPT = (
    "Identifique qual é a espécie desta ave (comum no Brasil) e retorne "
    'o nome científico e popular em formato JSON, usando as chaves '
    '"scientific_name" e "common_name"'
)

# Prompt da bioacústica: a entrada é um **espectrograma** (o "canto desenhado"
# no tempo × frequência) e não uma foto. Explicamos isso à IA para que ela
# interprete o padrão acústico (trilhas harmônicas, sílabas) como faria o
# BirdNET, devolvendo os mesmos campos em JSON.
SPECTROGRAM_PROMPT = (
    "A imagem é um **espectrograma** de um canto de ave (eixo horizontal = tempo, "
    "eixo vertical = frequência). Interprete o padrão acústico (sílabas, trilhas "
    "harmônicas e frequências dominantes) e identifique a espécie mais provável "
    "(fauna brasileira quando possível). Retorne apenas JSON com as chaves "
    '"scientific_name" e "common_name".'
)
# Tamanho máximo da mensagem de erro do provedor exibida ao usuário.
_MAX_DETAIL = 200


class ExternalIdentificationError(RuntimeError):
    """Erro seguro e sem dados sensíveis ao consultar a API externa."""


@dataclass(frozen=True)
class SpeciesIdentification:
    scientific_name: str
    common_name: str


def detect_provider(provider: str | None, base_url: str | None = None) -> str:
    """Resolve o provedor efetivo a partir do campo e/ou da URL base.

    Um provedor explícito (``google``/``gemini`` → Google; qualquer outro →
    compatível com a OpenAI) sempre vence. Quando ele está vazio, a URL base é
    usada como pista — mantendo a compatibilidade com configurações antigas que
    só guardavam a URL (ex.: ``generativelanguage.googleapis.com``).
    """
    cleaned = (provider or "").strip().lower()
    if cleaned:
        if cleaned in {PROVIDER_GOOGLE, "gemini"}:
            return PROVIDER_GOOGLE
        return PROVIDER_OPENAI
    if "generativelanguage.googleapis.com" in (base_url or "").lower():
        return PROVIDER_GOOGLE
    return PROVIDER_OPENAI


def is_google_provider(provider: str | None, base_url: str | None = None) -> bool:
    """Atalho: o provedor efetivo é o Google Gemini?"""
    return detect_provider(provider, base_url) == PROVIDER_GOOGLE


def default_model_for(provider: str | None, base_url: str | None = None) -> str:
    """Modelo padrão do provedor efetivo (Gemini x compatível com a OpenAI)."""
    if is_google_provider(provider, base_url):
        return GOOGLE_DEFAULT_MODEL
    return OPENAI_DEFAULT_MODEL


def normalize_base_url(base_url: str | None) -> str:
    """Normaliza e valida a URL base do provedor compatível com a OpenAI.

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


def normalize_google_base_url(base_url: str | None) -> str:
    """Devolve a base oficial do Google Gemini.

    O endpoint do Google **não** usa a URL compatível com a OpenAI. Quando a URL
    informada aponta para o Google, aproveitamos o host e garantimos a versão da
    API no fim (removendo um eventual sufixo ``/openai``); caso contrário, a URL
    é **ignorada** e usamos o endereço oficial do Google.
    """
    cleaned = (base_url or "").strip().rstrip("/")
    if cleaned and "generativelanguage.googleapis.com" in cleaned.lower():
        cleaned = re.sub(r"/openai$", "", cleaned, flags=re.IGNORECASE)
        if not re.search(r"/v\d+[a-z]*\d*$", cleaned, flags=re.IGNORECASE):
            cleaned = f"{cleaned}/{GOOGLE_API_VERSION}"
        return cleaned
    return GOOGLE_DEFAULT_BASE_URL


def google_generate_content_url(
    model: str | None, base_url: str | None = None
) -> str:
    """URL do endpoint oficial ``generateContent`` do Google Gemini."""
    base = normalize_google_base_url(base_url)
    modelo = (model or GOOGLE_DEFAULT_MODEL).strip()
    return f"{base}/models/{modelo}:generateContent"


def chat_completions_url(base_url: str | None = None) -> str:
    """URL do endpoint de chat completions do provedor compatível com OpenAI."""
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
    if isinstance(error, str):
        return error.strip()[:_MAX_DETAIL]
    if isinstance(data.get("message"), str):
        return data["message"].strip()[:_MAX_DETAIL]
    return ""


def connection_test_request(
    provider: str | None,
    base_url: str | None,
    model: str | None,
    api_key: str,
) -> tuple[str, dict[str, str], dict[str, str] | None, dict[str, object]]:
    """Monta a requisição mínima para validar chave/URL/modelo do provedor.

    Devolve ``(url, headers, params, payload)`` já no formato correto: o
    endpoint oficial ``generateContent`` do Google (com a chave em ``key``) ou o
    ``/chat/completions`` compatível com a OpenAI. A listagem ``/models`` não
    serve para o teste: em vários provedores ela é pública e responde 200 mesmo
    com uma chave inválida.
    """
    if is_google_provider(provider, base_url):
        url = google_generate_content_url(model, base_url)
        payload: dict[str, object] = {
            "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
            "generationConfig": {"maxOutputTokens": 8},
        }
        return url, {"Content-Type": "application/json"}, {"key": api_key}, payload

    url = chat_completions_url(base_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or OPENAI_DEFAULT_MODEL,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    return url, headers, None, payload


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
    *,
    google: bool = False,
) -> requests.Response:
    """POST seguro ao provedor.

    No Google a chave vai na *query string* (``?key=``) e **não** há cabeçalho
    ``Authorization``; nos demais provedores usamos ``Bearer``.
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}
    params: dict[str, str] | None = None
    if google:
        params = {"key": api_key}
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        return requests.post(
            url,
            headers=headers,
            params=params,
            json=payload,
            timeout=(10, 45),
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise ExternalIdentificationError(
            "Não foi possível conectar à API externa de identificação"
        ) from exc


def _google_payload(
    image_base64: str, prompt: str = IDENTIFICATION_PROMPT
) -> dict[str, object]:
    """Corpo da requisição ``generateContent`` com a imagem em base64."""
    return {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {
                        "inline_data": {
                            "mime_type": "image/jpeg",
                            "data": image_base64,
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.0,
        },
    }


def _google_text(response_data: dict[str, object]) -> str:
    """Extrai o texto das ``candidates`` da resposta do Gemini."""
    candidatos = response_data.get("candidates")
    if not isinstance(candidatos, list) or not candidatos:
        return ""
    primeiro = candidatos[0]
    if not isinstance(primeiro, dict):
        return ""
    conteudo = primeiro.get("content")
    if not isinstance(conteudo, dict):
        return ""
    partes = conteudo.get("parts")
    if not isinstance(partes, list):
        return ""
    return "".join(
        str(parte.get("text", "")) for parte in partes if isinstance(parte, dict)
    )


def _openai_content(response_data: dict[str, object]) -> str:
    """Extrai o conteúdo textual da resposta compatível com a OpenAI."""
    escolhas = response_data["choices"]  # type: ignore[index]
    conteudo = escolhas[0]["message"]["content"]  # type: ignore[index]
    # Alguns provedores devolvem o conteúdo como lista de partes.
    if isinstance(conteudo, list):
        conteudo = "".join(
            str(parte.get("text", ""))
            for parte in conteudo
            if isinstance(parte, dict)
        )
    return str(conteudo)


def identify_bird_image(
    image_bytes: bytes, prompt: str = IDENTIFICATION_PROMPT
) -> SpeciesIdentification:
    """Identifica a espécie de uma imagem usando o provedor configurado.

    ``prompt`` permite reaproveitar o mesmo motor tanto para a foto da ave
    (padrão) quanto para o **espectrograma** da detecção sonora
    (:data:`SPECTROGRAM_PROMPT`).
    """
    settings = get_settings()
    if not settings.ai_external_api_key:
        raise ExternalIdentificationError(
            "Configure AI_EXTERNAL_API_KEY para habilitar a identificação externa"
        )
    if not image_bytes:
        raise ExternalIdentificationError("O recorte da ave está vazio")

    provider = detect_provider(
        settings.ai_external_provider, settings.ai_external_base_url
    )
    model = settings.ai_external_model or default_model_for(provider)
    api_key = settings.ai_external_api_key
    image_base64 = base64.b64encode(image_bytes).decode("ascii")

    if provider == PROVIDER_GOOGLE:
        url = google_generate_content_url(model, settings.ai_external_base_url)
        payload = _google_payload(image_base64, prompt)
        response = _post(url, api_key, payload, google=True)
        # Alguns proxies do Gemini não aceitam "responseMimeType"; tenta de novo.
        if response.status_code == 400 and "responsemimetype" in response.text.lower():
            config = payload.get("generationConfig")
            if isinstance(config, dict):
                config.pop("responseMimeType", None)
            response = _post(url, api_key, payload, google=True)
    else:
        try:
            url = chat_completions_url(settings.ai_external_base_url)
        except ValueError as exc:
            raise ExternalIdentificationError(str(exc)) from exc
        payload = {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
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
        response = _post(url, api_key, payload)
        # Alguns provedores não suportam "response_format"; tenta novamente sem ele.
        if response.status_code == 400 and "response_format" in response.text.lower():
            payload.pop("response_format", None)
            response = _post(url, api_key, payload)

    if not 200 <= response.status_code < 300:
        detail = redact_secrets(provider_error_detail(response), [api_key])
        message = (
            f"A API externa de identificação respondeu com HTTP "
            f"{response.status_code}"
        )
        if detail:
            message = f"{message}: {detail}"
        raise ExternalIdentificationError(message)

    try:
        response_data = response.json()
        content = (
            _google_text(response_data)
            if provider == PROVIDER_GOOGLE
            else _openai_content(response_data)
        )
        identification = _parse_identification(content)
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


def identify_bird_image_file(path: Path | str) -> SpeciesIdentification:
    """Utilitário: envia uma imagem já tratada (arquivo) para a IA externa.

    Pensado para reaproveitar a **foto otimizada** do pipeline de gravação — a
    thumbnail oficial em alta definição ou o recorte tratado da ave — como
    entrada da identificação ultra-específica (ex.: Google Gemini Vision). Lê o
    arquivo do disco e delega para :func:`identify_bird_image`, mantendo o mesmo
    tratamento de erros seguro.
    """
    caminho = Path(path)
    try:
        image_bytes = caminho.read_bytes()
    except OSError as exc:
        raise ExternalIdentificationError(
            "Não foi possível ler a imagem tratada da ave"
        ) from exc
    return identify_bird_image(image_bytes)


def identify_spectrogram(image_bytes: bytes) -> SpeciesIdentification:
    """Identifica a espécie a partir do **espectrograma** de uma detecção sonora.

    Reaproveita o mesmo motor da visão, mas com o prompt de bioacústica
    (:data:`SPECTROGRAM_PROMPT`), orientando a IA a interpretar o padrão
    acústico desenhado no tempo × frequência.
    """
    return identify_bird_image(image_bytes, prompt=SPECTROGRAM_PROMPT)


# --------------------------------------------------------------------------- #
# Consulta ornitológica profunda (ficha técnica da espécie)
# --------------------------------------------------------------------------- #

# Campos textuais esperados no JSON devolvido pela IA externa.
_CONSULT_TEXT_FIELDS = (
    "scientific_name",
    "common_name",
    "family",
    "order",
    "conservation_status",
    "diet",
    "feeding_behavior",
    "habitat",
    "distribution",
    "biogeography",
    "migration",
    "size_cm",
    "weight_g",
    "lifespan",
    "notes",
)


def build_consult_prompt(common_name: str, scientific_name: str) -> str:
    """Monta o prompt ornitológico rico usado na consulta profunda da espécie.

    Pede uma ficha estruturada (JSON) com nome científico, família, status de
    conservação, comportamento alimentar, habitat, curiosidades e dados
    biogeográficos — o conteúdo exibido no modal de consulta do Bem-Te-Vi.
    """
    nome = (common_name or "").strip() or "ave não identificada"
    cientifico = (scientific_name or "").strip() or "não informado"
    return (
        "Você é um ornitólogo especialista na avifauna do Brasil (Mata Atlântica "
        "e Sul do Brasil). Produza uma ficha técnica profunda e confiável sobre a "
        f'espécie "{nome}" (nome científico: {cientifico}).\n'
        "Responda SOMENTE com um JSON válido, em português do Brasil, sem "
        "nenhum texto fora do JSON, usando exatamente estas chaves:\n"
        "{\n"
        '  "scientific_name": "nome científico binomial",\n'
        '  "common_name": "nome popular em português",\n'
        '  "family": "família taxonômica (ex.: Thraupidae)",\n'
        '  "order": "ordem taxonômica (ex.: Passeriformes)",\n'
        '  "conservation_status": "status de conservação (IUCN e/ou nacional)",\n'
        '  "diet": "dieta (ex.: frugívora, insetívora, granívora, nectarívora)",\n'
        '  "feeding_behavior": "comportamento alimentar e uso de comedouros",\n'
        '  "habitat": "habitat e ambientes frequentados",\n'
        '  "distribution": "distribuição geográfica",\n'
        '  "biogeography": "dados biogeográficos e ocorrência no Sul do Brasil",\n'
        '  "migration": "comportamento migratório / sazonalidade",\n'
        '  "size_cm": "comprimento típico em centímetros",\n'
        '  "weight_g": "peso típico em gramas",\n'
        '  "lifespan": "expectativa de vida aproximada",\n'
        '  "curiosities": ["curiosidade 1", "curiosidade 2", "curiosidade 3"],\n'
        '  "notes": "observações científicas e dicas de identificação"\n'
        "}\n"
        "Seja preciso e objetivo. Quando não souber um campo, use uma string "
        "vazia (ou uma lista vazia, no caso de curiosities)."
    )


@dataclass(frozen=True)
class SpeciesConsult:
    """Ficha ornitológica estruturada devolvida pela IA externa."""

    data: dict[str, Any]
    provider: str
    model: str

    def as_dict(self) -> dict[str, Any]:
        """Devolve os campos da ficha (sem os metadados da consulta)."""
        return dict(self.data)


def _normalize_consult(
    raw: dict[str, Any], *, common_name: str, scientific_name: str
) -> dict[str, Any]:
    """Normaliza o JSON devolvido pela IA para o formato do Bem-Te-Vi.

    Tolera listas onde se espera texto e vice-versa, garante que os nomes
    popular/científico nunca fiquem vazios e limita o número de curiosidades.
    """

    def _texto(chave: str) -> str:
        valor = raw.get(chave)
        if valor is None:
            return ""
        if isinstance(valor, (list, tuple)):
            return "; ".join(
                str(item).strip() for item in valor if str(item).strip()
            )
        return str(valor).strip()

    curiosidades_brutas = raw.get("curiosities")
    curiosidades: list[str] = []
    if isinstance(curiosidades_brutas, list):
        curiosidades = [
            str(item).strip()
            for item in curiosidades_brutas
            if str(item).strip()
        ]
    elif isinstance(curiosidades_brutas, str) and curiosidades_brutas.strip():
        curiosidades = [curiosidades_brutas.strip()]

    data = {chave: _texto(chave) for chave in _CONSULT_TEXT_FIELDS}
    data["scientific_name"] = data["scientific_name"] or scientific_name.strip()
    data["common_name"] = data["common_name"] or common_name.strip()
    data["curiosities"] = curiosidades[:6]
    return data


def consult_species_profile(
    *,
    common_name: str,
    scientific_name: str,
    image_bytes: bytes | None = None,
) -> SpeciesConsult:
    """Consulta a IA externa e devolve a ficha ornitológica profunda da espécie.

    Reaproveita o mesmo roteamento de provedor da identificação (Google Gemini
    oficial × compatível com a OpenAI). Quando uma imagem tratada é informada,
    ela é enviada junto ao prompt para enriquecer a resposta (plumagem/porte).
    """
    settings = get_settings()
    if not settings.ai_external_api_key:
        raise ExternalIdentificationError(
            "Configure AI_EXTERNAL_API_KEY para habilitar a consulta externa"
        )

    provider = detect_provider(
        settings.ai_external_provider, settings.ai_external_base_url
    )
    model = settings.ai_external_model or default_model_for(provider)
    api_key = settings.ai_external_api_key
    prompt = build_consult_prompt(common_name, scientific_name)
    image_base64 = (
        base64.b64encode(image_bytes).decode("ascii") if image_bytes else None
    )

    if provider == PROVIDER_GOOGLE:
        url = google_generate_content_url(model, settings.ai_external_base_url)
        parts: list[dict[str, object]] = [{"text": prompt}]
        if image_base64:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64,
                    }
                }
            )
        payload: dict[str, object] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
            },
        }
        response = _post(url, api_key, payload, google=True)
        # Alguns proxies do Gemini não aceitam "responseMimeType"; tenta de novo.
        if response.status_code == 400 and "responsemimetype" in response.text.lower():
            config = payload.get("generationConfig")
            if isinstance(config, dict):
                config.pop("responseMimeType", None)
            response = _post(url, api_key, payload, google=True)
    else:
        try:
            url = chat_completions_url(settings.ai_external_base_url)
        except ValueError as exc:
            raise ExternalIdentificationError(str(exc)) from exc
        content: list[dict[str, object]] = [{"type": "text", "text": prompt}]
        if image_base64:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}",
                        "detail": "high",
                    },
                }
            )
        payload = {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": content}],
        }
        response = _post(url, api_key, payload)
        # Alguns provedores não suportam "response_format"; tenta sem ele.
        if response.status_code == 400 and "response_format" in response.text.lower():
            payload.pop("response_format", None)
            response = _post(url, api_key, payload)

    if not 200 <= response.status_code < 300:
        detail = redact_secrets(provider_error_detail(response), [api_key])
        message = (
            f"A API externa de consulta respondeu com HTTP {response.status_code}"
        )
        if detail:
            message = f"{message}: {detail}"
        raise ExternalIdentificationError(message)

    try:
        response_data = response.json()
        content = (
            _google_text(response_data)
            if provider == PROVIDER_GOOGLE
            else _openai_content(response_data)
        )
        raw = _parse_identification(content)
        if not isinstance(raw, dict):
            raise ValueError("A resposta não é um objeto JSON")
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        raise ExternalIdentificationError(
            "A API externa retornou uma ficha ornitológica em formato inválido"
        ) from exc

    data = _normalize_consult(
        raw, common_name=common_name, scientific_name=scientific_name
    )
    return SpeciesConsult(data=data, provider=provider, model=model)
