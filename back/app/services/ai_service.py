"""Serviço de Inteligência Artificial Externa — Google Gemini (provedor único).

Este módulo é o **único** ponto de contato do Bem-Te-Vi com a IA externa.
Todas as identificações de aves por imagem/espectrograma e todas as consultas
ornitológicas profundas usam exclusivamente a biblioteca oficial
``google-genai`` (sucessor do ``google-generativeai``) com o modelo Gemini
selecionado pelo observador.

Destaques:

* **Sanitização do nome do modelo** (:func:`sanitize_model_name`): remove o
  prefixo ``models/`` (e afins) que o painel ou uma configuração antiga possa
  ter gravado. Sem isso, a API oficial responde **404 NOT_FOUND**, pois espera
  apenas o nome curto (``gemini-3.5-flash``).
* **Backoff exponencial** nas falhas temporárias (429/503) do serviço do Google.
* **Fallback automático**: se o modelo configurado responder 404, o serviço
  percorre :data:`app.core.gemini.GEMINI_MODELS` (começando pelos modelos
  validados) antes de desistir.
* **Mensagens amigáveis** em português do Brasil, sem vazar a chave da API.
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.core.gemini import (
    GEMINI_DEFAULT_MODEL,
    GEMINI_FALLBACK_MODEL,
    GEMINI_MODEL_PRESETS,
    GEMINI_MODELS,
    MODELOS_DESCONTINUADOS,
)
from app.core.redaction import redact_secrets

try:  # pragma: no cover - dependência do SDK oficial do Google
    from google.api_core.exceptions import ResourceExhausted
except Exception:  # pragma: no cover - fallback quando o SDK não está instalado

    class ResourceExhausted(Exception):  # type: ignore[no-redef]
        """Placeholder usado quando ``google-api-core`` não está disponível."""


logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Modelos suportados
# --------------------------------------------------------------------------- #
# As constantes de modelo vivem em :mod:`app.core.gemini` para serem
# compartilhadas com o domínio (schemas da API) sem duplicar literais.
# Elas continuam acessíveis como ``ai_service.GEMINI_*`` (re-export), o que
# preserva a compatibilidade com imports existentes.

#: Pausa (segundos) entre as tentativas automáticas — evita sobrecarregar a
#: chave e o AI Studio durante o teste de conexão.
RETRY_PAUSE_SECONDS = 2.0

#: Mensagem amigável para o limite de requisições do Google AI Studio (429).
QUOTA_MESSAGE = (
    "Limite de requisições por minuto atingido no Google AI Studio "
    "(Erro 429). Aguarde 30 a 60 segundos e tente novamente."
)

#: Prefixos inválidos aceitos por engano no campo de modelo.
_MODEL_PREFIXES = ("models/", "model/", "tunedModels/", "publishers/google/models/")

# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #

IDENTIFICATION_PROMPT = (
    "Identifique qual é a espécie desta ave (comum no Brasil) e retorne "
    'o nome científico e popular em formato JSON, usando as chaves '
    '"scientific_name" e "common_name"'
)

SPECTROGRAM_PROMPT = (
    "A imagem é um **espectrograma** de um canto de ave (eixo horizontal = tempo, "
    "eixo vertical = frequência). Interprete o padrão acústico (sílabas, trilhas "
    "harmônicas e frequências dominantes) e identifique a espécie mais provável "
    "(fauna brasileira quando possível). Retorne apenas JSON com as chaves "
    '"scientific_name" e "common_name".'
)

#: Prompt leve usado pelo botão "Testar Conexão com Gemini".
CONNECTION_TEST_PROMPT = "Responda apenas: OK"

#: Orçamento de saída padrão das chamadas ao Gemini.
#:
#: Atenção: nos modelos Gemini 3.x os **tokens de raciocínio** ("thinking")
#: são descontados do mesmo ``max_output_tokens`` da resposta. Com 1024 o
#: modelo gastava ~979 tokens pensando e sobravam ~41 para o JSON, que era
#: truncado (``finish_reason=MAX_TOKENS``) — origem do erro "formato inválido".
DEFAULT_MAX_OUTPUT_TOKENS = 2048

#: Ficha ornitológica: raciocínio (~1.100 tokens) + JSON completo (~750).
CONSULT_MAX_OUTPUT_TOKENS = 4096

#: Teto da expansão automática quando o modelo ainda truncar a resposta.
MAX_OUTPUT_TOKENS_CEILING = 8192

#: Campos textuais esperados no JSON devolvido pelo Gemini.
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


class ExternalIdentificationError(RuntimeError):
    """Erro seguro e sem dados sensíveis ao consultar o Gemini."""


@dataclass(frozen=True)
class SpeciesIdentification:
    """Resultado da identificação de uma ave pelo Gemini."""

    scientific_name: str
    common_name: str


@dataclass(frozen=True)
class SpeciesConsult:
    """Ficha ornitológica estruturada devolvida pelo Gemini."""

    data: dict[str, Any]
    model: str
    #: Provedor efetivo — sempre "google" (único provedor suportado).
    provider: str = "google"

    def as_dict(self) -> dict[str, Any]:
        """Devolve os campos da ficha (sem os metadados da consulta)."""
        return dict(self.data)


# --------------------------------------------------------------------------- #
# Sanitização e utilitários
# --------------------------------------------------------------------------- #


def sanitize_model_name(model_name: str | None) -> str:
    """Normaliza o nome do modelo Gemini, removendo prefixos inválidos.

    O painel (ou uma configuração antiga) pode gravar ``models/gemini-3.5-flash``.
    A API oficial do Google espera **apenas** ``gemini-3.5-flash``; enviar o
    prefixo provoca ``404 NOT_FOUND``. Esta função resolve o caso de forma
    determinística, sem I/O.

    Como o **Google Gemini é o único provedor suportado**, um nome que não
    pertença à família ``gemini-*`` (por exemplo, o legado ``gpt-4o-mini`` de
    instalações antigas) é substituído pelo modelo padrão — evitando o
    ``404 NOT_FOUND`` logo após a migração.

    >>> sanitize_model_name("models/gemini-3.5-flash")
    'gemini-3.5-flash'
    >>> sanitize_model_name("  GEMINI-2.5-FLASH  ")
    'GEMINI-2.5-FLASH'
    >>> sanitize_model_name("gpt-4o-mini")
    'gemini-3.5-flash'
    """
    cleaned = (model_name or "").strip()
    if not cleaned:
        return GEMINI_DEFAULT_MODEL

    # Remove barras à esquerda e prefixos repetidos (ex.: "models/models/x").
    changed = True
    while changed:
        changed = False
        for prefix in _MODEL_PREFIXES:
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix) :].strip()
                changed = True

    # Só o nome do modelo (sem sufixos de versão como ":latest" ou parâmetros).
    cleaned = cleaned.split(":", 1)[0].strip()

    if not cleaned:
        return GEMINI_DEFAULT_MODEL
    # Modelo de outro provedor (configuração legada): volta ao padrão do Gemini.
    if not cleaned.lower().startswith("gemini"):
        logger.warning(
            "Modelo %s não pertence ao Google Gemini; usando %s.",
            cleaned,
            GEMINI_DEFAULT_MODEL,
        )
        return GEMINI_DEFAULT_MODEL

    # Aviso informativo (não bloqueia): a cadeia de fallback cuidará do 404.
    if cleaned.lower() in MODELOS_DESCONTINUADOS:
        logger.info(
            "O modelo %s foi descontinuado pelo Google; a cadeia de fallback "
            "vai migrar automaticamente para %s.",
            cleaned,
            GEMINI_DEFAULT_MODEL,
        )
    return cleaned


def _is_model_not_found(exc: BaseException) -> bool:
    """O erro do Gemini indica 404 (modelo inexistente/renomeado)?"""
    code = getattr(exc, "code", None)
    if code in (404,):
        return True
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 404:
        return True
    text = str(exc).lower()
    return "404" in text or "not found" in text or "not_found" in text


def _is_auth_error(exc: BaseException) -> bool:
    """O erro do Gemini indica 401/403 (chave inválida ou sem permissão)?"""
    code = getattr(exc, "code", None)
    if code in (401, 403):
        return True
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) in (401, 403):
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in ("401", "403", "api key not valid", "permission denied", "unauthorized")
    )


def _is_quota_error(exc: BaseException) -> bool:
    """O erro indica cota insuficiente (429 RESOURCE_EXHAUSTED)?

    Nesse caso **trocar de modelo não ajuda** — a cota é da chave, não do
    modelo. O serviço apenas repete a mesma chamada com backoff.
    """
    code = getattr(exc, "code", None)
    if code == 429:
        return True
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) == 429:
        return True
    text = str(exc).lower()
    return "resource exhausted" in text or "quota" in text


def _is_temporary_error(exc: BaseException) -> bool:
    """O erro do Gemini indica 429/503 (instabilidade temporária)?"""
    if _is_quota_error(exc):
        return True
    code = getattr(exc, "code", None)
    if code in (429, 500, 502, 503, 504):
        return True
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) in (429, 500, 502, 503, 504):
        return True
    text = str(exc).lower()
    return any(
        marker in text
        for marker in ("429", "503", "overloaded", "resource exhausted", "unavailable", "deadline")
    )


def _client(api_key: str) -> Any:
    """Instancia o cliente oficial ``google-genai`` com a chave informada."""
    try:
        from google import genai
    except ImportError as exc:  # pragma: no cover - dependência obrigatória
        raise ExternalIdentificationError(
            "A biblioteca google-genai não está instalada. "
            "Execute: pip install google-genai"
        ) from exc
    return genai.Client(api_key=api_key)


def list_available_models(api_key: str) -> list[str]:
    """Descobre os modelos Gemini realmente disponíveis para a chave informada.

    Usa ``client.models.list()`` do SDK oficial. O Google descontinua modelos
    com frequência, então listar a API é a única forma de oferecer um
    dropdown que **funciona** para a chave do observador.

    Devolve a lista ordenada por prioridade (Flash antes de Pro) e, se a
    chamada falhar, os presets :data:`GEMINI_MODEL_PRESETS` como fallback.
    """
    fallback = [modelo for modelo, _ in GEMINI_MODEL_PRESETS]
    try:
        client = _client((api_key or "").strip())
        encontrados: list[str] = []
        for item in client.models.list():
            nome = str(getattr(item, "name", "") or "")
            if not nome:
                continue
            # Só interessa o que suporta ``generateContent`` (visão/texto).
            acoes = getattr(item, "supported_actions", None) or []
            if acoes and "generateContent" not in acoes:
                continue
            modelo = nome.split("/")[-1].strip()
            if modelo.lower().startswith("gemini") and modelo not in encontrados:
                encontrados.append(modelo)
    except Exception:
        logger.debug("Não foi possível listar os modelos do Gemini", exc_info=True)
        return fallback

    if not encontrados:
        return fallback

    # Prioriza: Flash (rápido) → Pro (denso) → demais, mantendo a ordem da API.
    def _chave(modelo: str) -> tuple[int, int, str]:
        nome = modelo.lower()
        if "flash-lite" in nome:
            familia = 0
        elif "flash" in nome:
            familia = 1
        elif "pro" in nome:
            familia = 2
        else:
            familia = 3
        return (familia, len(nome), modelo)

    return sorted(encontrados, key=_chave)


def _extract_suggested_model(exc: BaseException) -> str | None:
    """Extrai o modelo sugerido pelo Google na mensagem de erro 404.

    O Google responde algo como *"...is no longer available to new users.
    Please update your code to use models/gemini-3.8-flash..."*. Seguir essa
    sugestão evita que o observador fique sem IA até corrigir a configuração.

    A mensagem também cita o modelo que **falhou** (``models/gemini-2.5-flash``),
    então procuramos primeiro a ocorrência depois de *"use "* — que é a
    recomendação — e só depois caímos para qualquer ``models/gemini-*``.
    """
    texto = str(exc)

    # Preferência: o modelo recomendado ("Please update your code to use models/X").
    recomendado = re.search(
        r"use\s+models/(gemini-[A-Za-z0-9._-]+)", texto, flags=re.IGNORECASE
    )
    if recomendado:
        return recomendado.group(1).strip().rstrip(".,;'\"")

    # Fallback: qualquer menção a um modelo Gemini.
    achado = re.search(r"models/(gemini-[A-Za-z0-9._-]+)", texto)
    if achado:
        return achado.group(1).strip().rstrip(".,;'\"")
    return None


def _model_candidates(model_name: str | None) -> list[str]:
    """Cadeia de modelos a tentar: o configurado + os presets validados."""
    configurado = sanitize_model_name(model_name)
    cadeia = [configurado]
    for modelo in GEMINI_MODELS:
        if modelo not in cadeia:
            cadeia.append(modelo)
    return cadeia


def _response_finish_reason(response: Any) -> str:
    """Devolve o motivo de término da resposta (``STOP``/``MAX_TOKENS``/…)."""
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ""
    motivo = getattr(candidates[0], "finish_reason", None)
    if motivo is None:
        return ""
    return str(getattr(motivo, "name", motivo)).upper()


def _generate(
    *,
    api_key: str,
    model_name: str,
    prompt: str,
    image_base64: str | None = None,
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
    temperature: float = 0.0,
    json_response: bool = True,
) -> str:
    """Chama o Gemini e devolve o texto puro da resposta.

    Estratégia de resiliência (o Google descontinua modelos e sobrecarrega os
    mais populares):

    1. **Backoff exponencial** (3 tentativas: 0s, 1s, 2s) em 429/503;
    2. **Cadeia de fallback:** se o modelo responder 404 (não existe mais),
       o serviço tenta o próximo modelo validado em :data:`GEMINI_MODELS`;
    3. **Sugestão do Google:** se a mensagem indicar outro modelo
       (``Please update your code to use models/gemini-X``), ele entra na
       frente da cadeia;
    4. **Resposta truncada:** se vier ``finish_reason=MAX_TOKENS`` (o Gemini
       3.x "pensa" dentro do mesmo orçamento), o orçamento é dobrado e a
       chamada repetida até :data:`MAX_OUTPUT_TOKENS_CEILING`.
    """
    from google.genai import types as genai_types

    client = _client(api_key)
    cadeia = _model_candidates(model_name)
    tentados: set[str] = set()
    last_error: BaseException | None = None

    def _call(target_model: str) -> str:
        orcamento = max_output_tokens
        while True:
            config_kwargs: dict[str, Any] = {
                "max_output_tokens": orcamento,
                "temperature": temperature,
            }
            if json_response:
                config_kwargs["response_mime_type"] = "application/json"
            parts: list[Any] = [genai_types.Part.from_text(text=prompt)]
            if image_base64:
                parts.append(
                    genai_types.Part.from_bytes(
                        data=base64.b64decode(image_base64),
                        mime_type="image/jpeg",
                    )
                )
            response = client.models.generate_content(
                model=target_model,
                contents=genai_types.Content(role="user", parts=parts),
                config=genai_types.GenerateContentConfig(**config_kwargs),
            )
            texto = (response.text or "").strip()
            if _response_finish_reason(response) == "MAX_TOKENS":
                if orcamento < MAX_OUTPUT_TOKENS_CEILING:
                    novo = min(orcamento * 2, MAX_OUTPUT_TOKENS_CEILING)
                    logger.warning(
                        "Resposta do Gemini truncada (MAX_TOKENS) no modelo %s; "
                        "ampliando max_output_tokens de %s para %s.",
                        target_model,
                        orcamento,
                        novo,
                    )
                    orcamento = novo
                    continue
                raise ExternalIdentificationError(
                    "A resposta da IA ficou incompleta (limite de tokens). "
                    "Tente novamente em instantes."
                )
            if not texto:
                raise ExternalIdentificationError(
                    "O Google Gemini devolveu uma resposta vazia. "
                    "Tente novamente em instantes."
                )
            return texto

    while cadeia:
        modelo = cadeia.pop(0)
        if modelo in tentados:
            continue
        tentados.add(modelo)
        cota_esgotada = False

        for tentativa in range(3):
            try:
                return _call(modelo)
            except ResourceExhausted as exc:
                # ---------------------------------------------------------------- #
                # 429 RESOURCE_EXHAUSTED — cota/limite de requisições do
                # Google AI Studio. Tratamento específico: a mensagem é
                # amigável e a pausa entre tentativas é fixa, para não
                # sobrecarregar ainda mais a chave.
                # ---------------------------------------------------------------- #
                last_error = exc
                logger.warning(
                    "Limite de requisições do Google AI Studio atingido (429) "
                    "no modelo %s (tentativa %s/3).",
                    modelo,
                    tentativa + 1,
                )
                if tentativa < 2:
                    time.sleep(RETRY_PAUSE_SECONDS)
                    continue
                cota_esgotada = True
                break
            except Exception as exc:
                last_error = exc
                # Mensagens já amigáveis e específicas (ex.: resposta truncada,
                # resposta vazia) sobem sem serem reembaladas.
                if isinstance(exc, ExternalIdentificationError):
                    raise
                if _is_auth_error(exc):
                    raise ExternalIdentificationError(
                        "Chave de API inválida. Verifique se copiou corretamente."
                    ) from exc
                if _is_model_not_found(exc):
                    logger.warning(
                        "Modelo Gemini %s indisponível (404); trocando de modelo.",
                        modelo,
                    )
                    # O Google pode sugerir outro modelo utilizável.
                    sugerido = _extract_suggested_model(exc)
                    if sugerido and sugerido not in tentados:
                        cadeia.insert(0, sugerido)
                    break  # passa para o próximo candidato
                if _is_temporary_error(exc) and tentativa < 2:
                    time.sleep(RETRY_PAUSE_SECONDS)
                    continue
                # Erro transitório persistente: tenta o próximo modelo —
                # mas só se for sobrecarga (503). Cota (429) é da chave, então
                # trocar de modelo não resolveria: encerra a cadeia.
                if _is_temporary_error(exc):
                    if _is_quota_error(exc):
                        logger.warning(
                            "Cota do Gemini esgotada no modelo %s.", modelo
                        )
                        cota_esgotada = True
                        break
                    logger.warning(
                        "Modelo Gemini %s sobrecarregado (%s); tentando o próximo.",
                        modelo,
                        getattr(exc, "code", "?"),
                    )
                break
        if cota_esgotada:
            break
        # fim do laço de tentativas deste modelo → próximo da cadeia

    detail = redact_secrets(str(last_error or "erro desconhecido"), [api_key])
    if last_error is not None and _is_quota_error(last_error):
        raise ExternalIdentificationError(QUOTA_MESSAGE) from last_error
    raise ExternalIdentificationError(
        f"A API do Google Gemini respondeu com erro: {detail[:200]}"
    ) from last_error


def _extract_json_object(text: str) -> str | None:
    """Extrai o primeiro objeto JSON **balanceado** de um texto.

    Tolera texto antes/depois do JSON (comum quando o modelo "pensa em voz
    alta") e chaves dentro de strings, sem depender de regex frágil.
    """
    inicio = text.find("{")
    if inicio < 0:
        return None
    profundidade = 0
    dentro_string = False
    escape = False
    for posicao in range(inicio, len(text)):
        caractere = text[posicao]
        if dentro_string:
            if escape:
                escape = False
            elif caractere == "\\":
                escape = True
            elif caractere == '"':
                dentro_string = False
            continue
        if caractere == '"':
            dentro_string = True
        elif caractere == "{":
            profundidade += 1
        elif caractere == "}":
            profundidade -= 1
            if profundidade == 0:
                return text[inicio : posicao + 1]
    return None


def _repair_json(text: str) -> str:
    """Corrige vírgulas sobrando antes de ``}``/``]`` (erro comum dos LLMs)."""
    return re.sub(r",\s*([}\]])", r"\1", text)


def _parse_json(content: str) -> dict[str, Any]:
    """Interpreta o JSON devolvido pelo Gemini de forma tolerante.

    Camadas de tolerância (da mais estrita para a mais permissiva):

    1. JSON puro;
    2. JSON dentro de cerca de código Markdown (```` ```json ````);
    3. primeiro objeto balanceado dentro de texto explicativo;
    4. correção de vírgulas finais;
    5. ``json.loads(..., strict=False)`` (aceita caracteres de controle).

    Levanta :class:`ValueError` com o motivo real quando nada funciona — o
    chamador transforma isso em uma mensagem amigável.
    """
    text = (content or "").strip()
    if not text:
        raise ValueError("Resposta vazia")

    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    candidatos: list[str] = [text]
    extraido = _extract_json_object(text)
    if extraido and extraido != text:
        candidatos.append(extraido)

    ultimo_erro: Exception | None = None
    for candidato in candidatos:
        for tentativa in (candidato, _repair_json(candidato)):
            try:
                data = json.loads(tentativa, strict=False)
            except (TypeError, ValueError) as exc:
                ultimo_erro = exc
                continue
            # Alguns modelos embrulham o objeto em uma lista de um item.
            if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
                return data[0]
            if not isinstance(data, dict):
                ultimo_erro = ValueError("A resposta não é um objeto JSON")
                continue
            return data

    raise ValueError(f"JSON inválido: {ultimo_erro}")


# --------------------------------------------------------------------------- #
# Identificação
# --------------------------------------------------------------------------- #


def identify_bird_image(
    image_bytes: bytes, prompt: str = IDENTIFICATION_PROMPT
) -> SpeciesIdentification:
    """Identifica a espécie de uma imagem usando o Google Gemini.

    ``prompt`` permite reaproveitar o mesmo motor tanto para a foto da ave
    (padrão) quanto para o **espectrograma** da detecção sonora
    (:data:`SPECTROGRAM_PROMPT`).
    """
    settings = get_settings()
    api_key = (settings.ai_external_api_key or "").strip()
    if not api_key:
        raise ExternalIdentificationError(
            "Configure a chave do Google Gemini (GEMINI_API_KEY) para habilitar "
            "a identificação externa"
        )
    if not image_bytes:
        raise ExternalIdentificationError("O recorte da ave está vazio")

    content = _generate(
        api_key=api_key,
        model_name=settings.ai_external_model,
        prompt=prompt,
        image_base64=base64.b64encode(image_bytes).decode("ascii"),
    )

    try:
        data = _parse_json(content)
        scientific_name = str(data["scientific_name"]).strip()
        common_name = str(data["common_name"]).strip()
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        logger.error(
            "Identificação inválida (%s). Prévia da resposta: %s",
            exc,
            redact_secrets(content[:400], [api_key]) or "<vazia>",
        )
        raise ExternalIdentificationError(
            "O Google Gemini retornou uma identificação em formato inválido"
        ) from exc

    if not scientific_name or not common_name:
        raise ExternalIdentificationError(
            "O Google Gemini não retornou os nomes científico e popular"
        )
    return SpeciesIdentification(
        scientific_name=scientific_name,
        common_name=common_name,
    )


def identify_bird_image_file(path: Path | str) -> SpeciesIdentification:
    """Envia uma imagem já tratada (arquivo) para o Google Gemini.

    Pensado para reaproveitar a **foto otimizada** do pipeline de gravação — a
    thumbnail oficial em alta definição ou o recorte tratado da ave — como
    entrada da identificação ultra-específica (Gemini Vision).
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
    """Identifica a espécie a partir do **espectrograma** de uma detecção sonora."""
    return identify_bird_image(image_bytes, prompt=SPECTROGRAM_PROMPT)


# --------------------------------------------------------------------------- #
# Consulta ornitológica profunda
# --------------------------------------------------------------------------- #


def build_consult_prompt(common_name: str, scientific_name: str) -> str:
    """Monta o prompt ornitológico rico usado na consulta profunda da espécie."""
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


def _normalize_consult(
    raw: dict[str, Any], *, common_name: str, scientific_name: str
) -> dict[str, Any]:
    """Normaliza o JSON devolvido pelo Gemini para o formato do Bem-Te-Vi."""

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
    """Consulta o Gemini e devolve a ficha ornitológica profunda da espécie.

    Quando uma imagem tratada é informada, ela é enviada junto ao prompt para
    enriquecer a resposta (plumagem/porte).
    """
    settings = get_settings()
    api_key = (settings.ai_external_api_key or "").strip()
    if not api_key:
        raise ExternalIdentificationError(
            "Configure a chave do Google Gemini (GEMINI_API_KEY) para habilitar "
            "a consulta externa"
        )

    content = _generate(
        api_key=api_key,
        model_name=settings.ai_external_model,
        prompt=build_consult_prompt(common_name, scientific_name),
        image_base64=(
            base64.b64encode(image_bytes).decode("ascii") if image_bytes else None
        ),
        # A ficha tem ~15 campos + raciocínio do modelo: 4096 é o mínimo
        # validado. Orçamentos menores truncavam o JSON (MAX_TOKENS).
        max_output_tokens=CONSULT_MAX_OUTPUT_TOKENS,
        temperature=0.2,
    )

    try:
        raw = _parse_json(content)
    except (TypeError, ValueError, AttributeError) as exc:
        logger.error(
            "Ficha ornitológica inválida (%s). Prévia da resposta: %s",
            exc,
            redact_secrets(content[:400], [api_key]) or "<vazia>",
        )
        raise ExternalIdentificationError(
            "O Google Gemini retornou uma ficha ornitológica incompleta ou em "
            "formato inválido. Tente novamente em instantes."
        ) from exc

    data = _normalize_consult(
        raw, common_name=common_name, scientific_name=scientific_name
    )
    return SpeciesConsult(
        data=data,
        model=sanitize_model_name(settings.ai_external_model),
        provider="google",
    )


# --------------------------------------------------------------------------- #
# Teste de conexão
# --------------------------------------------------------------------------- #


def test_gemini_connection(
    api_key: str,
    model_name: str | None = None,
    *,
    max_attempts: int = 3,
) -> tuple[bool, str]:
    """Testa a chave/modelo do Google Gemini com um prompt mínimo.

    Devolve ``(ok, mensagem)`` — a mensagem é sempre amigável e já pronta para
    exibição no painel (nunca vaza a chave).

    * Sucesso → *"Conexão perfeita! A IA respondeu corretamente."*
    * 401/403 → *"Chave de API inválida. Verifique se copiou corretamente."*
    * 429/503 (após 3 tentativas) → *"A chave está correta, mas os servidores
      do Google estão superlotados neste exato segundo. Pode salvar, vai
      funcionar depois!"*
    * 404 em toda a cadeia → *"O modelo informado não existe mais no Google
      Gemini..."* com a lista de modelos válidos.
    """
    chave = (api_key or "").strip()
    if not chave:
        return False, "Informe a chave da API do Google Gemini para testar."

    modelo = sanitize_model_name(model_name)

    for attempt in range(max_attempts):
        try:
            texto = _generate(
                api_key=chave,
                model_name=modelo,
                prompt=CONNECTION_TEST_PROMPT,
                max_output_tokens=256,
                temperature=0.0,
                json_response=False,
            )
        except ExternalIdentificationError as exc:
            mensagem = str(exc)
            if "Chave de API inválida" in mensagem:
                return False, mensagem
            # 429 (ResourceExhausted) — cota/limite por minuto do AI Studio.
            if QUOTA_MESSAGE in mensagem:
                return False, QUOTA_MESSAGE
            if "resposta com erro" in mensagem:
                if "404" in mensagem or "NOT_FOUND" in mensagem.upper():
                    return False, (
                        "O modelo informado não existe mais no Google Gemini. "
                        f"Use um destes: {', '.join(GEMINI_MODELS)}."
                    )
                if "503" in mensagem or "UNAVAILABLE" in mensagem.upper():
                    if attempt < max_attempts - 1:
                        time.sleep(RETRY_PAUSE_SECONDS)
                        continue
                    return False, (
                        "A chave está correta, mas os servidores do Google estão "
                        "superlotados neste exato segundo. Pode salvar, vai "
                        "funcionar depois!"
                    )
            return False, mensagem
        else:
            if "OK" in texto.upper():
                return True, "Conexão perfeita! A IA respondeu corretamente."
            if texto:
                return True, (
                    "Conexão validada! O Google Gemini respondeu normalmente."
                )
            return True, (
                "Conexão validada! O Google Gemini respondeu (sem texto na "
                "amostra, o que é normal no teste rápido)."
            )

    return False, (
        "A chave está correta, mas os servidores do Google estão superlotados "
        "neste exato segundo. Pode salvar, vai funcionar depois!"
    )
