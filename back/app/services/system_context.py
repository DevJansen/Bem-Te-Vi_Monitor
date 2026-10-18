"""Contexto sistêmico da IA: ajuste de sensibilidade por clima e horário.

A IA local "entende" o estado do Bem-Ti-Vi e adapta a sensibilidade:

- **Calibração do usuário** é a base (nunca elevamos a confiança acima dela).
- **Clima adverso** (chuva, nevoeiro, tempestade, nublado) reduz a visibilidade:
  o motor fica mais permissivo (limiar menor), liga o *filtro de contraste
  adaptativo* e, nos casos mais severos, um *Test-Time Augmentation* leve.
- **Noite / baixa luz** também relaxa o limiar (a visão noturna já realça o
  contraste antes da inferência).

O ajuste é sempre **conservador**: só *abaixa* o limiar efetivo, jamais o sobe,
para não silenciar detecções que o usuário configurou.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Fatores multiplicativos aplicados à confiança base (menor = mais permissivo).
_FATOR_CLIMA_SEVERO = 0.85  # chuva, nevoeiro, tempestade
_FATOR_NUBLADO = 0.92  # céu encoberto, sem chuva
_FATOR_NOITE = 0.90  # baixa luz

# Categorias meteorológicas (ver app/services/weather_service.py).
_CATEGORIAS_SEVERAS = {"Chuva", "Nevoeiro", "Tempestade", "Neve"}


@dataclass
class AjusteContexto:
    """Resultado do ajuste contextual aplicado à detecção."""

    confianca_efetiva: float
    # Se o Test-Time Augmentation leve deve ser ligado nesta inferência.
    tta: bool = False
    # Se o filtro de contraste adaptativo (CLAHE) deve preceder a inferência.
    contraste_adaptativo: bool = False
    # Motivos legíveis (para telemetria/depuração).
    motivos: list[str] = field(default_factory=list)

    def resumo(self) -> str:
        return ", ".join(self.motivos) if self.motivos else "condições normais"


def _clamp(valor: float, minimo: float = 0.05, maximo: float = 1.0) -> float:
    return min(maximo, max(minimo, float(valor)))


def ajustar_sensibilidade(
    confianca_base: float,
    *,
    categoria_clima: str | None = None,
    noite: bool = False,
) -> AjusteContexto:
    """Calcula a confiança efetiva e os realces conforme o contexto.

    Nunca retorna valor acima de ``confianca_base`` (respeita a calibração).
    """
    settings = get_settings()
    base = _clamp(confianca_base)
    if not bool(settings.adaptive_context_enabled):
        return AjusteContexto(confianca_efetiva=base, motivos=[])

    fator = 1.0
    motivos: list[str] = []
    tta = False
    contraste = False

    categoria = (categoria_clima or "").strip()
    if categoria in _CATEGORIAS_SEVERAS:
        fator *= _FATOR_CLIMA_SEVERO
        contraste = True
        tta = True
        motivos.append(f"clima adverso ({categoria}): +sensibilidade e contraste")
    elif categoria == "Nublado":
        fator *= _FATOR_NUBLADO
        contraste = True
        motivos.append("céu encoberto: contraste adaptativo")

    if noite:
        fator *= _FATOR_NOITE
        motivos.append("baixa luz: limiar relaxado")

    efetiva = _clamp(base * fator, minimo=0.05, maximo=base)
    return AjusteContexto(
        confianca_efetiva=efetiva,
        tta=tta,
        contraste_adaptativo=contraste,
        motivos=motivos,
    )


def clima_atual_categoria() -> str | None:
    """Categoria ampla do clima atual (ou ``None`` se indisponível).

    Nunca levanta exceção: sem rede/Open-Meteo, devolve ``None`` e o ajuste cai
    apenas no fator de noite.
    """
    try:
        from app.services.weather_service import get_weather_service

        snapshot = get_weather_service().current()
        if snapshot is None or not snapshot.available:
            return None
        return snapshot.category
    except Exception:
        logger.debug("Clima indisponível para o ajuste contextual", exc_info=True)
        return None
