"""Detecção de movimento inicial para acionar a inferência do YOLO.

Ideia: em cenas sem nenhuma ave rastreada, só vale a pena rodar o YOLO quando
algo se move (uma ave chegando ao comedouro). A `MOTION_SENSITIVITY` define o
quão sutil pode ser esse movimento:

- Sensibilidade alta  -> detecta pequenas mudanças (aves distantes/pequenas).
- Sensibilidade baixa -> exige movimento maior (menos ruído de fundo).

Observação: quando já existe uma ave rastreada, o pipeline ignora este portão e
continua rodando o YOLO, para não perder aves que ficaram imóveis.
"""

from __future__ import annotations

import cv2
import numpy as np

# Fração de pixels alterados exigida na sensibilidade mínima (0) e máxima (1).
MOTION_MAX_RATIO = 0.02  # 2,0% dos pixels — movimento evidente
MOTION_MIN_RATIO = 0.0002  # 0,02% dos pixels — movimento sutil


class MotionDetector:
    """Compara quadros consecutivos e informa se houve movimento relevante."""

    def __init__(self, sensitivity: float = 0.5) -> None:
        self._previous: np.ndarray | None = None
        self._sensitivity = min(1.0, max(0.0, float(sensitivity)))

    def set_sensitivity(self, sensitivity: float) -> None:
        self._sensitivity = min(1.0, max(0.0, float(sensitivity)))

    @property
    def threshold(self) -> float:
        """Fração mínima de pixels alterados para considerar que houve movimento."""
        return MOTION_MAX_RATIO - self._sensitivity * (
            MOTION_MAX_RATIO - MOTION_MIN_RATIO
        )

    def reset(self) -> None:
        self._previous = None

    def detect(self, frame: np.ndarray) -> bool:
        """Retorna True se o quadro atual difere o suficiente do anterior."""
        if frame is None or frame.size == 0:
            return False

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Suaviza para reduzir ruído de sensor/compressão.
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if self._previous is None or self._previous.shape != gray.shape:
            self._previous = gray
            return False

        difference = cv2.absdiff(self._previous, gray)
        self._previous = gray
        _, changed = cv2.threshold(difference, 25, 255, cv2.THRESH_BINARY)
        changed_ratio = float(np.count_nonzero(changed)) / float(changed.size)
        return changed_ratio >= self.threshold
