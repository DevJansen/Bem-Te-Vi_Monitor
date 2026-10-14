"""
Hook / structure for a secondary species classifier.

Stage 2 ships a pass-through implementation that labels detections as generic
'bird'. Swap in a fine-tuned model later without changing the pipeline contract.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SpeciesPrediction:
    species: str
    confidence: float
    extras: dict[str, Any] | None = None


class SpeciesClassifier(ABC):
    """Secondary classifier interface (runs after YOLO bird detection)."""

    @abstractmethod
    def is_ready(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def classify(
        self,
        frame: np.ndarray,
        bbox: tuple[float, float, float, float],
    ) -> SpeciesPrediction:
        raise NotImplementedError


class PassthroughSpeciesClassifier(SpeciesClassifier):
    """Default stub — keeps the pipeline local and dependency-light."""

    def __init__(self, default_species: str = "bird") -> None:
        self.default_species = default_species

    def is_ready(self) -> bool:
        return True

    def classify(
        self,
        frame: np.ndarray,
        bbox: tuple[float, float, float, float],
    ) -> SpeciesPrediction:
        _ = frame, bbox  # crop available for future models
        return SpeciesPrediction(species=self.default_species, confidence=1.0)


class HookableSpeciesClassifier(SpeciesClassifier):
    """
    Wrapper that delegates to an optional callable/model.

    Example future wiring:
        classifier = HookableSpeciesClassifier(model=MyBirdNet())
    """

    def __init__(
        self,
        model: Any | None = None,
        fallback: SpeciesClassifier | None = None,
    ) -> None:
        self.model = model
        self.fallback = fallback or PassthroughSpeciesClassifier()

    def is_ready(self) -> bool:
        if self.model is None:
            return self.fallback.is_ready()
        return True

    def set_model(self, model: Any | None) -> None:
        self.model = model
        logger.info("Secondary species classifier model %s", "set" if model else "cleared")

    def classify(
        self,
        frame: np.ndarray,
        bbox: tuple[float, float, float, float],
    ) -> SpeciesPrediction:
        if self.model is None:
            return self.fallback.classify(frame, bbox)

        try:
            # Expected duck-typed API: model.predict(crop) -> (species, confidence)
            x1, y1, x2, y2 = [int(v) for v in bbox]
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w - 1, x2), min(h - 1, y2)
            crop = frame[y1:y2, x1:x2]
            if crop.size == 0:
                return self.fallback.classify(frame, bbox)

            if hasattr(self.model, "predict"):
                result = self.model.predict(crop)
            elif callable(self.model):
                result = self.model(crop)
            else:
                return self.fallback.classify(frame, bbox)

            if isinstance(result, SpeciesPrediction):
                return result
            if isinstance(result, tuple) and len(result) >= 2:
                return SpeciesPrediction(species=str(result[0]), confidence=float(result[1]))
            if isinstance(result, dict):
                return SpeciesPrediction(
                    species=str(result.get("species", "bird")),
                    confidence=float(result.get("confidence", 0.0)),
                    extras=result,
                )
            return SpeciesPrediction(species=str(result), confidence=0.0)
        except Exception:
            logger.exception("Secondary species classifier failed — using fallback")
            return self.fallback.classify(frame, bbox)


def get_default_species_classifier() -> SpeciesClassifier:
    return HookableSpeciesClassifier()
