"""Detector de aves com YOLOv8 (classe COCO 'bird').

Ajustes de sensibilidade:
- O limiar de confiança pode chegar a 0.05, permitindo detectar aves com menor
  grau de certeza visual (câmeras distantes, contraluz, pouca luz).
- A inferência é restrita à classe de ave do COCO (id 14), o que remove o ruído
  de fundo e evita contabilizar objetos que não são pássaros.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Id da classe "bird" no dataset COCO padrão e nome exibido no rótulo.
BIRD_CLASS_ID = 14
BIRD_CLASS_NAME = "bird"

# Faixa aceita para o limiar de confiança do YOLO.
CONFIDENCE_MIN = 0.05
CONFIDENCE_MAX = 1.0


@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    # Caixa no formato xyxy em pixels absolutos.
    bbox: tuple[float, float, float, float]

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox
        return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)

    def normalized_center(self, width: int, height: int) -> tuple[float, float]:
        cx, cy = self.center
        return (cx / max(width, 1), cy / max(height, 1))

    def as_list(self) -> list[float]:
        return [float(v) for v in self.bbox]


def clamp_confidence(value: float) -> float:
    """Garante que o limiar fique dentro da faixa suportada pelo detector."""
    return min(CONFIDENCE_MAX, max(CONFIDENCE_MIN, float(value)))


class BirdDetector:
    """Envelope thread-safe em torno do Ultralytics YOLOv8."""

    def __init__(
        self,
        model_name: str | None = None,
        confidence: float | None = None,
        bird_class_id: int | None = None,
    ) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.yolo_model
        # Sensibilidade inicial: vem do .env, mas é sobrescrita em runtime pelo
        # serviço de calibração (ver app/services/calibration.py).
        self.confidence = clamp_confidence(
            confidence if confidence is not None else settings.yolo_confidence
        )
        # Classe alvo da inferência (14 = "bird" no COCO).
        self.bird_class_id = int(
            bird_class_id
            if bird_class_id is not None
            else settings.yolo_bird_class_id
        )
        self._model = None
        self._lock = threading.RLock()
        self._load_error: str | None = None
        self._load_attempted = False

    @property
    def ready(self) -> bool:
        return self._model is not None

    @property
    def load_error(self) -> str | None:
        return self._load_error

    def set_confidence(self, value: float) -> None:
        """Atualiza o limiar de confiança em tempo real (thread-safe)."""
        self.confidence = clamp_confidence(value)

    def load(self, *, force: bool = False) -> bool:
        with self._lock:
            if self._model is not None:
                return True
            if self._load_attempted and not force:
                return False
            self._load_attempted = True
            try:
                from ultralytics import YOLO

                logger.info("Carregando modelo YOLO %s (inferência local)", self.model_name)
                self._model = YOLO(self.model_name)
                self._load_error = None
                return True
            except Exception as exc:
                self._load_error = str(exc)
                logger.exception("Falha ao carregar o modelo YOLO %s", self.model_name)
                return False

    def detect(self, frame: np.ndarray) -> list[Detection]:
        if frame is None or frame.size == 0:
            return []
        with self._lock:
            if self._model is None:
                if not self.load():
                    return []
            try:
                results = self._model.predict(
                    source=frame,
                    # Aplica o limiar calibrado (com o piso de segurança da faixa).
                    conf=clamp_confidence(self.confidence),
                    # Filtro de classe: somente aves (COCO id 14).
                    classes=[self.bird_class_id],
                    verbose=False,
                )
            except Exception:
                logger.exception("Falha na inferência do YOLO")
                return []

        detections: list[Detection] = []
        try:
            for result in results:
                boxes = getattr(result, "boxes", None)
                if boxes is None:
                    continue
                for box in boxes:
                    cls_id = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                    xyxy = box.xyxy[0].tolist()
                    name = BIRD_CLASS_NAME
                    try:
                        name = result.names.get(cls_id, BIRD_CLASS_NAME)
                    except Exception:
                        pass
                    detections.append(
                        Detection(
                            class_id=cls_id,
                            class_name=str(name),
                            confidence=conf,
                            bbox=(float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])),
                        )
                    )
        except Exception:
            logger.exception("Falha ao interpretar o resultado do YOLO")
            return []
        return detections


_detector: BirdDetector | None = None
_detector_lock = threading.Lock()


def get_bird_detector() -> BirdDetector:
    global _detector
    with _detector_lock:
        if _detector is None:
            _detector = BirdDetector()
        return _detector
