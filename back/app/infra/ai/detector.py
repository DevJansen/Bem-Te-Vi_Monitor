"""YOLOv8 bird detector (COCO class 'bird')."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# COCO class id for bird
BIRD_CLASS_ID = 14
BIRD_CLASS_NAME = "bird"


@dataclass
class Detection:
    class_id: int
    class_name: str
    confidence: float
    # xyxy absolute pixels
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


class BirdDetector:
    """Thread-safe wrapper around Ultralytics YOLOv8."""

    def __init__(self, model_name: str | None = None, confidence: float | None = None) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.yolo_model
        self.confidence = min(
            1.0,
            max(0.60, confidence if confidence is not None else settings.yolo_confidence),
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

    def load(self, *, force: bool = False) -> bool:
        with self._lock:
            if self._model is not None:
                return True
            if self._load_attempted and not force:
                return False
            self._load_attempted = True
            try:
                from ultralytics import YOLO

                logger.info("Loading YOLO model %s (local inference only)", self.model_name)
                self._model = YOLO(self.model_name)
                self._load_error = None
                return True
            except Exception as exc:
                self._load_error = str(exc)
                logger.exception("Failed to load YOLO model %s", self.model_name)
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
                    conf=min(1.0, max(0.60, self.confidence)),
                    classes=[BIRD_CLASS_ID],
                    verbose=False,
                )
            except Exception:
                logger.exception("YOLO inference failed")
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
            logger.exception("Failed to parse YOLO results")
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
