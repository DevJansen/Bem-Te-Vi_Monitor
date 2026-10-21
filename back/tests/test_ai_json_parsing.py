"""Testes de regressão — parsing da ficha ornitológica do Google Gemini.

Contexto do bug: nos modelos Gemini 3.x os *tokens de raciocínio* ("thinking")
consomem o mesmo ``max_output_tokens`` da resposta. Com o orçamento antigo de
1024, sobravam ~41 tokens para o JSON, que era truncado no meio
(``finish_reason=MAX_TOKENS``) e virava o erro
*"O Google Gemini retornou uma ficha ornitológica em formato inválido"*.

Estes testes são **offline** (não chamam a API) e cobrem:

* o parsing tolerante (:func:`app.services.ai_service._parse_json`);
* a leitura de ``finish_reason`` (:func:`_response_finish_reason`);
* os orçamentos mínimos de saída definidos em :mod:`app.services.ai_service`.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from app.services.ai_service import (
    CONSULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_OUTPUT_TOKENS,
    MAX_OUTPUT_TOKENS_CEILING,
    _parse_json,
    _response_finish_reason,
)


# --------------------------------------------------------------------------- #
# Parsing tolerante
# --------------------------------------------------------------------------- #


def test_parse_json_puro():
    """JSON limpo continua funcionando."""
    assert _parse_json('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_parse_json_com_cerca_markdown():
    """Modelos às vezes devolvem o JSON dentro de ```json ... ```."""
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_com_texto_ao_redor():
    """Texto explicativo antes/depois do objeto deve ser ignorado."""
    bruto = 'Claro! Aqui está:\n{"a": 1, "b": {"c": 2}}\nEspero ter ajudado.'
    assert _parse_json(bruto) == {"a": 1, "b": {"c": 2}}


def test_parse_json_com_virgula_final():
    """Vírgula sobrando antes de ``}``/``]`` (erro comum dos LLMs)."""
    assert _parse_json('{"a": 1, "b": [1, 2,],}') == {"a": 1, "b": [1, 2]}


def test_parse_json_lista_de_um_objeto():
    """Alguns modelos embrulham o objeto em uma lista de um item."""
    assert _parse_json('[{"a": 1}]') == {"a": 1}


def test_parse_json_chaves_dentro_de_string():
    """Chaves dentro de strings não devem confundir o extrator."""
    assert _parse_json('{"a": "texto { com } chaves", "b": 2}') == {
        "a": "texto { com } chaves",
        "b": 2,
    }


def test_parse_json_truncado_falha_com_motivo():
    """JSON cortado no meio deve falhar (e o chamador gera a mensagem amigável)."""
    truncado = '{"scientific_name": "Turdus rufiventris", "family":'
    try:
        _parse_json(truncado)
    except ValueError as exc:
        assert "JSON inválido" in str(exc)
    else:  # pragma: no cover - falha explícita se não levantar
        raise AssertionError("JSON truncado deveria levantar ValueError")


def test_parse_json_vazio_falha():
    """Resposta vazia deve falhar com mensagem clara."""
    try:
        _parse_json("   ")
    except ValueError as exc:
        assert "vazia" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("Resposta vazia deveria levantar ValueError")


# --------------------------------------------------------------------------- #
# finish_reason
# --------------------------------------------------------------------------- #


@dataclass
class _Candidato:
    finish_reason: object


def test_finish_reason_max_tokens():
    """Deve extrair ``MAX_TOKENS`` do enum do SDK oficial."""
    resposta = SimpleNamespace(
        candidates=[_Candidato(finish_reason=SimpleNamespace(name="MAX_TOKENS"))]
    )
    assert _response_finish_reason(resposta) == "MAX_TOKENS"


def test_finish_reason_stop_e_ausente():
    """``STOP`` é preservado; resposta sem candidatos devolve string vazia."""
    resposta = SimpleNamespace(
        candidates=[_Candidato(finish_reason=SimpleNamespace(name="STOP"))]
    )
    assert _response_finish_reason(resposta) == "STOP"
    assert _response_finish_reason(SimpleNamespace(candidates=[])) == ""


# --------------------------------------------------------------------------- #
# Orçamento de tokens (regressão do bug)
# --------------------------------------------------------------------------- #


def test_orcamento_da_ficha_e_suficiente():
    """A ficha ornitológica precisa de espaço para raciocínio + JSON."""
    assert DEFAULT_MAX_OUTPUT_TOKENS >= 2048
    assert CONSULT_MAX_OUTPUT_TOKENS >= 4096
    assert MAX_OUTPUT_TOKENS_CEILING > CONSULT_MAX_OUTPUT_TOKENS
