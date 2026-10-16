"""Pré-processamento de imagem para visão noturna (infravermelho / baixa luz).

Câmeras de segurança com infravermelho entregam, à noite, imagens em tons de
cinza e com pouca luminância. O YOLOv8 é treinado em fotos coloridas e bem
iluminadas e, nesse cenário, perde bastante precisão. Este módulo realça o
contraste local (CLAHE) e reduz o ruído antes da inferência, ajudando o
detector a enxergar formas mesmo no escuro — sem alterar o modelo treinado.

Modos de operação (ver :class:`app.domain.models.NightVisionMode`):

- ``auto`` (padrão): só aplica o realce quando a luminância média do quadro
  fica abaixo do limiar configurado (detecção automática de baixa luz).
- ``on``: aplica sempre — útil para câmeras IR que não escurecem o suficiente.
- ``off``: desliga o realce; os quadros seguem crus para a inferência.

O processamento é leve o bastante para rodar a cada quadro do pipeline: o
realce é pulado por completo em cenas claras (modo ``auto``), restando apenas o
cálculo da luminância, feito sobre uma versão reduzida do quadro.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import cv2
import numpy as np

from app.domain.models import NightVisionMode

logger = logging.getLogger(__name__)

# Fator de redução usado apenas para estimar a luminância média (barato).
_BRIGHTNESS_SCALE = 0.1


@dataclass
class NightVisionResult:
    """Resultado do pré-processamento de um quadro.

    - ``frame``: quadro a ser usado dali em diante (realçado ou original).
    - ``brightness``: luminância média estimada (0-255).
    - ``low_light``: se a cena foi considerada escura.
    - ``applied``: se o realce de visão noturna foi de fato aplicado.
    """

    frame: np.ndarray
    brightness: float
    low_light: bool
    applied: bool


class NightVisionProcessor:
    """Realce de contraste (CLAHE) e redução de ruído para cenas escuras."""

    def __init__(
        self,
        *,
        mode: object = NightVisionMode.AUTO,
        threshold: float = 60.0,
        clahe_clip: float = 2.5,
        clahe_grid: int = 8,
        denoise: bool = True,
    ) -> None:
        self._lock = threading.RLock()
        self._mode = NightVisionMode.normalize(mode)
        self._threshold = float(threshold)
        self._denoise = bool(denoise)
        self._clahe_clip = float(clahe_clip)
        self._clahe_grid = int(clahe_grid)
        self._clahe = self._build_clahe(self._clahe_clip, self._clahe_grid)

    # ------------------------------------------------------------------ #
    # Configuração em tempo de execução
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_clahe(clip: float, grid: int) -> cv2.CLAHE:
        size = max(2, int(grid))
        return cv2.createCLAHE(
            clipLimit=max(1.0, float(clip)),
            tileGridSize=(size, size),
        )

    def configure(
        self,
        *,
        mode: object | None = None,
        threshold: float | None = None,
        clahe_clip: float | None = None,
        clahe_grid: int | None = None,
    ) -> None:
        """Atualiza os parâmetros sem reiniciar o pipeline (thread-safe)."""
        with self._lock:
            if mode is not None:
                self._mode = NightVisionMode.normalize(mode)
            if threshold is not None:
                self._threshold = float(threshold)
            if clahe_clip is not None or clahe_grid is not None:
                if clahe_clip is not None:
                    self._clahe_clip = float(clahe_clip)
                if clahe_grid is not None:
                    self._clahe_grid = int(clahe_grid)
                self._clahe = self._build_clahe(self._clahe_clip, self._clahe_grid)

    @property
    def mode(self) -> NightVisionMode:
        with self._lock:
            return self._mode

    @property
    def threshold(self) -> float:
        with self._lock:
            return self._threshold

    # ------------------------------------------------------------------ #
    # Processamento
    # ------------------------------------------------------------------ #
    @staticmethod
    def measure_brightness(frame: np.ndarray) -> float:
        """Estima a luminância média (0-255) a partir de uma versão reduzida."""
        if frame is None or frame.size == 0:
            return 0.0
        try:
            small = cv2.resize(
                frame,
                None,
                fx=_BRIGHTNESS_SCALE,
                fy=_BRIGHTNESS_SCALE,
                interpolation=cv2.INTER_AREA,
            )
        except cv2.error:
            small = frame
        gray = (
            cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            if small.ndim == 3
            else small
        )
        return float(gray.mean())

    def process(self, frame: np.ndarray) -> NightVisionResult:
        """Aplica o realce quando necessário e devolve o quadro a ser usado."""
        if frame is None or frame.size == 0:
            return NightVisionResult(
                frame=frame, brightness=0.0, low_light=False, applied=False
            )

        with self._lock:
            mode = self._mode
            threshold = self._threshold
            denoise = self._denoise
            clahe = self._clahe

        brightness = self.measure_brightness(frame)
        low_light = brightness < threshold

        # Modo "off" nunca realça; no "auto" só quando a cena está escura.
        if mode is NightVisionMode.OFF or (
            mode is NightVisionMode.AUTO and not low_light
        ):
            return NightVisionResult(
                frame=frame,
                brightness=brightness,
                low_light=low_light,
                applied=False,
            )

        try:
            # Garante 3 canais (câmeras IR puras podem entregar 1 canal).
            work = frame if frame.ndim == 3 else cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            if denoise:
                # Median blur 3x3: rápido e eficaz contra o ruído de sensor.
                work = cv2.medianBlur(work, 3)
            # CLAHE apenas no canal de luminosidade (L do espaço LAB), preservando
            # as cores. Em imagens IR (cinza) o resultado é um cinza realçado.
            lab = cv2.cvtColor(work, cv2.COLOR_BGR2LAB)
            lightness, a_chan, b_chan = cv2.split(lab)
            lightness = clahe.apply(lightness)
            enhanced = cv2.cvtColor(
                cv2.merge((lightness, a_chan, b_chan)), cv2.COLOR_LAB2BGR
            )
        except cv2.error:
            logger.exception("Falha ao aplicar visão noturna; usando o quadro original")
            return NightVisionResult(
                frame=frame,
                brightness=brightness,
                low_light=low_light,
                applied=False,
            )

        return NightVisionResult(
            frame=enhanced,
            brightness=brightness,
            low_light=low_light,
            applied=True,
        )
