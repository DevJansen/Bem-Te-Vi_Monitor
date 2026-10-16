"""Seleção automática do "melhor quadro" de uma visita.

Durante a janela de gravação (3 s antes + 3 s depois do gatilho), o pipeline
avalia cada quadro em que a ave aparece e guarda apenas o melhor. O critério
combina três sinais complementares:

- **Nitidez (variância do Laplaciano):** calculada sobre o recorte da caixa
  delimitadora da ave. Frames borrados (asa em movimento, foco perdido) têm
  variância baixa e perdem pontos. É o critério principal.
- **Confiança do YOLOv8:** um quadro em que o detector está mais seguro
  tende a ser uma pose mais "limpa" da ave.
- **Enquadramento (área ocupada):** premia uma proporção ideal da tela — nem
  um pontinho distante, nem um recorte colado na lente. A pontuação cai de
  forma suave (gaussiana) conforme a proporção se afasta do ideal.

O módulo é puro (sem I/O) e determinístico, o que o torna fácil de testar. Ele
guarda em memória apenas UM quadro (o melhor até agora), copiado sob demanda —
nada de acumular dezenas de frames de alta resolução.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from app.infra.ai.detector import Detection

# Pesos do escore combinado (somam 1.0). A nitidez domina, como pede o
# requisito de escolher o quadro mais nítido; confiança e enquadramento
# desempatam quadros com nitidez parecida.
PESO_NITIDEZ = 0.55
PESO_CONFIANCA = 0.30
PESO_ENQUADRAMENTO = 0.15

# Escala de normalização da variância do Laplaciano. A nitidez é mapeada para
# (0, 1) por `v / (v + escala)`: monotônica (preserva a ordenação) e estável,
# já que a variância absoluta varia muito entre câmeras/resoluções.
ESCALA_NITIDEZ_PADRAO = 120.0
# Proporção ideal da tela que a ave deve ocupar no melhor quadro.
PROPORCAO_IDEAL_PADRAO = 0.08
# Abertura da gaussiana do enquadramento (quanto maior, mais tolerante).
SIGMA_AREA_PADRAO = 0.10
# Proporção mínima para a ave ser considerada "fotografável" (evita salvar um
# recorte de poucos pixels, sem informação visual útil).
PROPORCAO_MINIMA_PADRAO = 0.0008
# Nitidez mínima (variância do Laplaciano) para aceitar um quadro. Abaixo disto
# o quadro é tratado como desfoque de movimento e DESCARTADO — só entra na foto
# final se nenhum quadro da janela passar no corte (aí usamos o melhor
# disponível, para nunca deixar a visita sem imagem).
NITIDEZ_MINIMA_PADRAO = 20.0


@dataclass
class MetricasQuadro:
    """Notas individuais de um quadro candidato (para log e auditoria)."""

    escore: float
    nitidez: float  # variância bruta do Laplaciano no recorte da ave
    nitidez_normalizada: float
    confianca: float
    proporcao_area: float
    escore_area: float


@dataclass
class MelhorQuadro:
    """Resultado da seleção: o quadro vencedor e o contexto da escolha."""

    frame: np.ndarray
    bbox: tuple[float, float, float, float]
    confianca: float
    class_id: int
    class_name: str
    metricas: MetricasQuadro
    # Verdadeiro quando o quadro passou no corte de nitidez (não é desfoque de
    # movimento). Falso apenas quando TODOS os quadros foram reprovados e este é
    # o melhor disponível (fallback).
    nitidez_aprovada: bool = True


def recorte_da_caixa(
    frame: np.ndarray, bbox: tuple[float, float, float, float]
) -> np.ndarray | None:
    """Devolve o recorte (view) da caixa ``xyxy``, já limitado ao quadro."""
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    altura, largura = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    esquerda = max(0, min(largura, int(math.floor(x1))))
    topo = max(0, min(altura, int(math.floor(y1))))
    direita = max(0, min(largura, int(math.ceil(x2))))
    base = max(0, min(altura, int(math.ceil(y2))))
    if direita <= esquerda or base <= topo:
        return None
    return frame[topo:base, esquerda:direita]


def variancia_laplaciano(imagem: np.ndarray) -> float:
    """Variância do operador Laplaciano — proxy clássico de nitidez.

    Quanto maior, mais arestas nítidas o recorte possui. Frames borrados têm
    variância baixa. Recortes minúsculos (< 3 px) não produzem medida confiável
    e retornam 0.
    """
    if imagem is None or getattr(imagem, "size", 0) == 0:
        return 0.0
    cinza = (
        cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
        if imagem.ndim == 3
        else imagem
    )
    if cinza.shape[0] < 3 or cinza.shape[1] < 3:
        return 0.0
    return float(cv2.Laplacian(cinza, cv2.CV_64F).var())


def _escore_area(proporcao: float, ideal: float, sigma: float) -> float:
    """Pontuação do enquadramento: 1.0 na proporção ideal, caindo suavemente."""
    sigma = max(float(sigma), 1e-6)
    return float(math.exp(-((proporcao - ideal) ** 2) / (2.0 * sigma * sigma)))


def avaliar_deteccao(
    frame: np.ndarray,
    detection: Detection,
    *,
    escala_nitidez: float = ESCALA_NITIDEZ_PADRAO,
    proporcao_ideal: float = PROPORCAO_IDEAL_PADRAO,
    sigma_area: float = SIGMA_AREA_PADRAO,
) -> MetricasQuadro | None:
    """Calcula o escore combinado de uma detecção em um quadro.

    Retorna ``None`` quando a caixa é inválida para o quadro (recorte vazio).
    """
    if frame is None or getattr(frame, "size", 0) == 0:
        return None
    altura, largura = frame.shape[:2]
    if largura <= 0 or altura <= 0:
        return None

    recorte = recorte_da_caixa(frame, detection.bbox)
    if recorte is None:
        return None

    nitidez = variancia_laplaciano(recorte)
    escala = max(float(escala_nitidez), 1e-6)
    nitidez_normalizada = nitidez / (nitidez + escala)

    x1, y1, x2, y2 = detection.bbox
    area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    proporcao = area / float(largura * altura)
    escore_area = _escore_area(proporcao, float(proporcao_ideal), float(sigma_area))

    confianca = max(0.0, min(1.0, float(detection.confidence)))
    escore = (
        PESO_NITIDEZ * nitidez_normalizada
        + PESO_CONFIANCA * confianca
        + PESO_ENQUADRAMENTO * escore_area
    )
    return MetricasQuadro(
        escore=escore,
        nitidez=nitidez,
        nitidez_normalizada=nitidez_normalizada,
        confianca=confianca,
        proporcao_area=proporcao,
        escore_area=escore_area,
    )


class SeletorMelhorQuadro:
    """Acumula candidatos ao longo da janela e retém o quadro de maior escore.

    Uso no pipeline: crie um seletor no gatilho e chame :meth:`considerar` a
    cada quadro da janela, passando as detecções rastreadas. Ao final, chame
    :meth:`resultado` para obter o quadro vencedor (ou ``None``).
    """

    def __init__(
        self,
        *,
        escala_nitidez: float = ESCALA_NITIDEZ_PADRAO,
        proporcao_ideal: float = PROPORCAO_IDEAL_PADRAO,
        sigma_area: float = SIGMA_AREA_PADRAO,
        proporcao_minima: float = PROPORCAO_MINIMA_PADRAO,
        nitidez_minima: float = NITIDEZ_MINIMA_PADRAO,
    ) -> None:
        self.escala_nitidez = float(escala_nitidez)
        self.proporcao_ideal = float(proporcao_ideal)
        self.sigma_area = float(sigma_area)
        self.proporcao_minima = float(proporcao_minima)
        self.nitidez_minima = float(nitidez_minima)
        # Duas trilhas: os quadros que passam no corte de nitidez e o melhor
        # absoluto (fallback para nunca ficar sem foto).
        self._melhor_aceito: MelhorQuadro | None = None
        self._melhor_absoluto: MelhorQuadro | None = None
        self._candidatos = 0
        self._descartados_por_nitidez = 0

    @property
    def candidatos(self) -> int:
        """Quantidade de detecções válidas avaliadas até agora."""
        return self._candidatos

    @property
    def descartados_por_nitidez(self) -> int:
        """Quadros rejeitados por desfoque de movimento (abaixo do limiar)."""
        return self._descartados_por_nitidez

    @property
    def tem_resultado(self) -> bool:
        return self._melhor_aceito is not None or self._melhor_absoluto is not None

    def considerar(
        self, frame: np.ndarray, deteccoes: list[Detection] | None
    ) -> None:
        """Avalia as detecções do quadro atual e atualiza o melhor, se melhorar."""
        if frame is None or getattr(frame, "size", 0) == 0:
            return
        for detection in deteccoes or []:
            metricas = avaliar_deteccao(
                frame,
                detection,
                escala_nitidez=self.escala_nitidez,
                proporcao_ideal=self.proporcao_ideal,
                sigma_area=self.sigma_area,
            )
            if metricas is None:
                continue
            if metricas.proporcao_area < self.proporcao_minima:
                continue
            self._candidatos += 1
            aprovado = metricas.nitidez >= self.nitidez_minima
            if not aprovado:
                self._descartados_por_nitidez += 1

            supera_absoluto = (
                self._melhor_absoluto is None
                or metricas.escore > self._melhor_absoluto.metricas.escore
            )
            supera_aceito = aprovado and (
                self._melhor_aceito is None
                or metricas.escore > self._melhor_aceito.metricas.escore
            )
            if not (supera_absoluto or supera_aceito):
                continue

            # Cópia sob demanda: só materializamos o quadro quando ele realmente
            # vence uma das trilhas, mantendo o uso de memória enxuto.
            candidato = MelhorQuadro(
                frame=frame.copy(),
                bbox=tuple(float(v) for v in detection.bbox),
                confianca=float(detection.confidence),
                class_id=int(detection.class_id),
                class_name=str(detection.class_name),
                metricas=metricas,
                nitidez_aprovada=aprovado,
            )
            if supera_absoluto:
                self._melhor_absoluto = candidato
            if supera_aceito:
                self._melhor_aceito = candidato

    def resultado(self) -> MelhorQuadro | None:
        """Devolve o melhor quadro aprovado na nitidez ou, na falta, o absoluto."""
        return self._melhor_aceito or self._melhor_absoluto
