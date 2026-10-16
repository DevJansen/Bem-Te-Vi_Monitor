"""Análise de comportamento: diferenciar *perching* de *feeding*.

Heurística de visão computacional (leve, sem novo modelo):

- **feeding (alimentando-se):** a ave está dentro de uma zona de comedouro/
  bebedouro (ROI com papel ``feeder``/``drinker``) **e** permanece quase imóvel
  (o bico está introduzido no comedouro, o corpo não se desloca).
- **perching (pousada):** a ave está imóvel, mas fora de uma zona de alimentação
  (ex.: apenas descansando no poleiro ao fundo).
- **moving (em movimento):** há deslocamento relevante (chegada, voo, disputa).

A "imobilidade" é medida pela energia de movimento dentro da caixa delimitadora
entre dois quadros consecutivos (diferença média em escala de cinza). É barato e
robusto para cenas de comedouro.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from app.domain.models import RoiType, RoiZone
from app.infra.ai.detector import Detection

# Papéis de ROI que caracterizam um ponto de alimentação.
ROLES_ALIMENTACAO = {"feeder", "drinker", "comedouro", "bebedouro"}

# Energia média (0-255) abaixo da qual a ave é considerada imóvel.
LIMIAR_MOVIMENTO_PADRAO = 8.0

TIPO_FEEDING = "feeding"
TIPO_PERCHING = "perching"
TIPO_MOVING = "moving"
TIPO_DESCONHECIDO = "desconhecido"

ROTULOS_PT: dict[str, str] = {
    TIPO_FEEDING: "Alimentando-se",
    TIPO_PERCHING: "Pousada",
    TIPO_MOVING: "Em movimento",
    TIPO_DESCONHECIDO: "Indeterminado",
}

ICONES: dict[str, str] = {
    TIPO_FEEDING: "🍽️",
    TIPO_PERCHING: "🐦",
    TIPO_MOVING: "✈️",
    TIPO_DESCONHECIDO: "❔",
}


@dataclass
class Comportamento:
    """Resultado da análise de comportamento de um quadro/janela."""

    tipo: str = TIPO_DESCONHECIDO
    zona_id: str | None = None
    zona_nome: str | None = None
    # Energia de movimento da ave mais relevante (menor energia = mais parada).
    energia: float | None = None
    detalhes: dict[str, Any] = field(default_factory=dict)

    @property
    def rotulo(self) -> str:
        return ROTULOS_PT.get(self.tipo, ROTULOS_PT[TIPO_DESCONHECIDO])

    @property
    def icone(self) -> str:
        return ICONES.get(self.tipo, ICONES[TIPO_DESCONHECIDO])

    def as_metadata(self) -> dict[str, Any]:
        return {
            "behavior": self.tipo,
            "behavior_label": self.rotulo,
            "behavior_icon": self.icone,
            "behavior_zone": self.zona_nome,
            "behavior_energy": (
                round(float(self.energia), 2) if self.energia is not None else None
            ),
        }


def energia_movimento(
    anterior_gray: np.ndarray | None,
    atual_gray: np.ndarray,
    bbox: tuple[float, float, float, float],
) -> float | None:
    """Energia de movimento (0-255) dentro da caixa entre dois quadros.

    Devolve ``None`` quando não há quadro anterior ou a caixa é degenerada.
    """
    if anterior_gray is None or atual_gray is None:
        return None
    altura, largura = atual_gray.shape[:2]
    x1, y1, x2, y2 = bbox
    xi1 = max(0, min(largura, int(x1)))
    yi1 = max(0, min(altura, int(y1)))
    xi2 = max(0, min(largura, int(x2)))
    yi2 = max(0, min(altura, int(y2)))
    if xi2 - xi1 < 2 or yi2 - yi1 < 2:
        return None
    if anterior_gray.shape[:2] != atual_gray.shape[:2]:
        return None
    recorte_atual = atual_gray[yi1:yi2, xi1:xi2]
    recorte_anterior = anterior_gray[yi1:yi2, xi1:xi2]
    diferenca = cv2.absdiff(recorte_atual, recorte_anterior)
    return float(np.mean(diferenca))


def _zona_que_contem(
    zonas: list[RoiZone], x: float, y: float
) -> RoiZone | None:
    """Primeira ROI de inclusão que contém o ponto normalizado."""
    for zona in zonas:
        if zona.type != RoiType.INCLUDE:
            continue
        if zona.contains(x, y):
            return zona
    return None


def classificar_comportamento(
    deteccoes: list[Detection],
    zonas_roi: list[RoiZone],
    *,
    largura: int,
    altura: int,
    energias: dict[int, float | None] | None = None,
    limiar_movimento: float = LIMIAR_MOVIMENTO_PADRAO,
) -> Comportamento:
    """Classifica o comportamento predominante no quadro.

    ``energias`` mapeia ``track_id`` → energia de movimento (de
    :func:`energia_movimento`). Sem esse mapa, cai para a ausência de dados e
    classifica como "em movimento".
    """
    if not deteccoes:
        return Comportamento(tipo=TIPO_DESCONHECIDO)

    melhor: Comportamento | None = None
    melhor_prioridade = -1

    for deteccao in deteccoes:
        centro_x, centro_y = deteccao.normalized_center(largura, altura)
        zona = _zona_que_contem(zonas_roi, centro_x, centro_y)
        energia = None
        if energias and deteccao.track_id is not None:
            energia = energias.get(deteccao.track_id)
        parada = energia is None or energia < limiar_movimento
        zona_alimentacao = (
            zona is not None and (zona.role or "").strip().lower() in ROLES_ALIMENTACAO
        )

        if zona_alimentacao and parada:
            tipo = TIPO_FEEDING
            prioridade = 3
        elif parada:
            tipo = TIPO_PERCHING
            prioridade = 2
        else:
            tipo = TIPO_MOVING
            prioridade = 1

        if prioridade > melhor_prioridade:
            melhor_prioridade = prioridade
            melhor = Comportamento(
                tipo=tipo,
                zona_id=zona.id if zona else None,
                zona_nome=zona.name if zona else None,
                energia=energia,
                detalhes={"track_id": deteccao.track_id},
            )

    return melhor or Comportamento(tipo=TIPO_DESCONHECIDO)
