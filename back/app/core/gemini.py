"""Constantes compartilhadas do **Google Gemini** (provedor único de IA externa).

Este módulo existe para que o *schema* da API (:mod:`app.domain.models`) e o
*cliente* do Gemini (:mod:`app.services.ai_service`) usem exatamente o mesmo
modelo padrão — sem literais duplicados que podem divergir com o tempo.

Por que isso importa: o Google **descontinua** modelos com frequência. Quando o
padrão do schema apontava para ``gemini-1.5-flash`` (descontinuado), o botão
"Testar conexão" fazia uma chamada inútil que respondia ``404 NOT_FOUND`` antes
de cair no modelo válido.

Este módulo **não importa nada do projeto** — pode ser usado por qualquer
camada (core, domain, services) sem risco de importação circular.
"""

from __future__ import annotations

#: Modelo padrão do Bem-Te-Vi (rápido, leve, com visão e **validado** na API).
#: Modelos antigos (``gemini-1.5-*``/``gemini-2.5-*``) foram descontinuados pelo
#: Google e respondem ``404 NOT_FOUND`` para chaves novas — usá-los como padrão
#: fazia a IA "quebrar" logo na primeira consulta.
GEMINI_DEFAULT_MODEL = "gemini-3.5-flash"

#: Presets exibidos no dropdown de Configurações — nomes oficiais da API do
#: Google Gemini. Servem de semente/fallback da interface; a lista real de
#: modelos disponíveis para a chave é descoberta em tempo de execução pela
#: API (:func:`app.services.ai_service.list_available_models`), porque o Google
#: descontinua modelos com frequência (vários deles respondem ``404``).
GEMINI_MODEL_PRESETS: tuple[tuple[str, str], ...] = (
    ("gemini-1.5-flash", "gemini-1.5-flash (Rápido, leve e estável)"),
    ("gemini-2.5-flash", "gemini-2.5-flash (Nova geração Flash)"),
    ("gemini-1.5-pro", "gemini-1.5-pro (Modo Pro — Análise densa)"),
)

#: Cadeia de fallback usada quando o modelo configurado não está disponível.
#: A ordem começa pelos modelos **validados** (3.x): assim uma configuração
#: antiga (ex.: ``gemini-2.5-flash``) cai direto em um modelo que responde, em
#: vez de gastar três chamadas 404 antes de funcionar.
GEMINI_MODELS: tuple[str, ...] = (
    GEMINI_DEFAULT_MODEL,
    "gemini-3.7-flash",
    "gemini-3.8-flash",
    "gemini-1.5-flash",
    "gemini-2.5-flash",
    "gemini-1.5-pro",
)

#: Modelos que o Google já descontinuou — mantidos apenas para migração
#: transparente (o serviço troca sozinho e registra um aviso no log).
MODELOS_DESCONTINUADOS: frozenset[str] = frozenset(
    {
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    }
)

#: Modelo usado como fallback quando o configurado responde 404.
GEMINI_FALLBACK_MODEL = GEMINI_DEFAULT_MODEL
