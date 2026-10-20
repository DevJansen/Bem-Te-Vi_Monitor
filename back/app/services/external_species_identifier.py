"""Identificação de aves sob demanda com o **Google Gemini** (provedor único).

Este módulo é mantido como **fachada retrocompatível**: toda a lógica vive
em :mod:`app.services.ai_service`, que usa exclusivamente a biblioteca oficial
``google-genai``. As funções exportadas aqui preservam os nomes históricos
usados pelos controllers (``identify_bird_image``, ``identify_spectrogram``,
``consult_species_profile``…), evitando breakage em toda a aplicação.

Nenhuma dependência de provedores OpenAI/Anthropic permanece: o Bem-Ti-Vi usa
**apenas** o Google Gemini.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.services.ai_service import (
    GEMINI_DEFAULT_MODEL,
    GEMINI_FALLBACK_MODEL,
    GEMINI_MODELS,
    ExternalIdentificationError,
    SpeciesConsult,
    SpeciesIdentification,
    build_consult_prompt,
    consult_species_profile,
    identify_bird_image,
    identify_bird_image_file,
    identify_spectrogram,
    sanitize_model_name,
    test_gemini_connection,
)

logger = logging.getLogger(__name__)

#: Provedor único suportado pelo Bem-Ti-Vi.
PROVIDER_GOOGLE = "google"

#: Alias legado (mantido só para compatibilidade com código antigo que
#: importava este nome). O valor é "google" — o provedor é único.
PROVIDER_OPENAI = "google"

#: URL base oficial do Google Generative Language.
GOOGLE_DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GOOGLE_API_VERSION = "v1beta"

#: Modelo padrão do Gemini.
GOOGLE_DEFAULT_MODEL = GEMINI_DEFAULT_MODEL


def detect_provider(provider: str | None = None, base_url: str | None = None) -> str:
    """Provedor efetivo — sempre ``google`` (único provedor suportado).

    Os parâmetros são mantidos apenas para compatibilidade com chamadas
    antigas; qualquer valor é normalizado para o Google Gemini.
    """
    return PROVIDER_GOOGLE


def is_google_provider(provider: str | None = None, base_url: str | None = None) -> bool:
    """Atalho: o provedor efetivo é sempre o Google Gemini."""
    return True


def default_model_for(provider: str | None = None, base_url: str | None = None) -> str:
    """Modelo padrão do Gemini."""
    return GEMINI_DEFAULT_MODEL


def normalize_base_url(base_url: str | None = None) -> str:
    """A URL base é fixa no endpoint oficial do Google."""
    return GOOGLE_DEFAULT_BASE_URL


def normalize_google_base_url(base_url: str | None = None) -> str:
    """A URL base é fixa no endpoint oficial do Google."""
    return GOOGLE_DEFAULT_BASE_URL


def google_generate_content_url(
    model: str | None = None, base_url: str | None = None
) -> str:
    """URL REST do ``generateContent`` (usada apenas em diagnóstico)."""
    modelo = sanitize_model_name(model)
    return f"{GOOGLE_DEFAULT_BASE_URL}/models/{modelo}:generateContent"


__all__ = [
    "ExternalIdentificationError",
    "GEMINI_DEFAULT_MODEL",
    "GEMINI_FALLBACK_MODEL",
    "GEMINI_MODELS",
    "GOOGLE_API_VERSION",
    "GOOGLE_DEFAULT_BASE_URL",
    "GOOGLE_DEFAULT_MODEL",
    "PROVIDER_GOOGLE",
    "SpeciesConsult",
    "SpeciesIdentification",
    "build_consult_prompt",
    "consult_species_profile",
    "default_model_for",
    "detect_provider",
    "google_generate_content_url",
    "identify_bird_image",
    "identify_bird_image_file",
    "identify_spectrogram",
    "is_google_provider",
    "normalize_base_url",
    "normalize_google_base_url",
    "sanitize_model_name",
    "test_gemini_connection",
]
