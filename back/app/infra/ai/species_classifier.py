"""Classificador secundário de espécies do Bem-Te-Vi Core.

O detector YOLOv8 (COCO) responde apenas “é uma ave?”. Este módulo é a segunda
etapa: recebe o recorte da ave e devolve a **espécie**. Quando existe um modelo
treinado pelo Aprendizado Ativo (``app-data/models/bem_te_vi_core.pt``), ele é
carregado automaticamente e passa a substituir o rótulo genérico ``bird`` no
pipeline ao vivo e na análise offline.

Sem modelo treinado — ou quando o ``ultralytics`` não está instalado — a classe
``HookableSpeciesClassifier`` delega ao ``PassthroughSpeciesClassifier`` e o
sistema continua funcionando exatamente como antes (rótulo genérico). O
contrato público (``classify(frame, bbox) -> SpeciesPrediction``) permanece
estável para o pipeline.
"""

from __future__ import annotations

import json
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SpeciesPrediction:
    """Resultado da classificação secundária de uma ave."""

    species: str
    confidence: float
    extras: dict[str, Any] | None = None


class SpeciesClassifier(ABC):
    """Interface do classificador secundário (executa após o YOLO)."""

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
    """Implementação padrão: mantém o pipeline local e sem dependências."""

    def __init__(self, default_species: str = "bird") -> None:
        self.default_species = default_species

    def is_ready(self) -> bool:
        return True

    def classify(
        self,
        frame: np.ndarray,
        bbox: tuple[float, float, float, float],
    ) -> SpeciesPrediction:
        _ = frame, bbox  # recorte disponível para modelos futuros
        return SpeciesPrediction(species=self.default_species, confidence=1.0)


class YoloClassificationModel:
    """Adaptador fino de um modelo YOLOv8 de **classificação** de espécies.

    O modelo é carregado de forma preguiçosa (primeira classificação) e a
    inferência é serializada por um lock: várias câmeras compartilham a mesma
    instância, mas o Ultralytics não garante segurança entre threads.
    """

    def __init__(self, model_path: str | Path) -> None:
        self.model_path = Path(model_path)
        self._lock = threading.Lock()
        self._model: Any | None = None
        self._labels: dict[str, str] = {}
        self._load_error: str | None = None
        self._load_labels()

    def _load_labels(self) -> None:
        """Carrega o mapa pasta→espécie original gravado no fine-tuning."""
        labels_path = get_settings().fine_tuned_labels_path
        if not labels_path.is_file():
            return
        try:
            payload = json.loads(labels_path.read_text(encoding="utf-8"))
            classes = payload.get("classes")
            if isinstance(classes, dict):
                self._labels = {
                    str(key): str(value) for key, value in classes.items()
                }
        except (OSError, TypeError, ValueError):
            logger.warning("Rótulos do modelo fine-tunado ilegíveis", exc_info=True)

    def _ensure_loaded(self) -> bool:
        if self._model is not None:
            return True
        if self._load_error is not None:
            return False
        if not self.model_path.is_file():
            self._load_error = "modelo ausente"
            return False
        try:
            from ultralytics import YOLO

            with self._lock:
                if self._model is None:
                    self._model = YOLO(str(self.model_path))
                    self._load_labels()
            logger.info(
                "Classificador de espécies fine-tunado carregado: %s",
                self.model_path,
            )
            return True
        except Exception as exc:
            self._load_error = str(exc)
            logger.exception(
                "Falha ao carregar o classificador fine-tunado %s",
                self.model_path,
            )
            return False

    def _display_species(self, name: Any) -> str:
        """Converte a classe do modelo no nome original e legível da espécie."""
        raw = str(name or "").strip()
        if not raw:
            return "bird"
        mapped = self._labels.get(raw)
        if mapped:
            return mapped
        # Pasta segura (sem acento/underscores) → texto apresentável.
        return raw.replace("_", " ").strip() or "bird"

    def predict(self, crop: np.ndarray) -> dict[str, Any]:
        """Classifica um recorte BGR. Devolve ``{"species", "confidence"}``."""
        if crop is None or crop.size == 0:
            return {"species": "bird", "confidence": 0.0}
        if not self._ensure_loaded() or self._model is None:
            return {"species": "bird", "confidence": 0.0}

        settings = get_settings()
        device = (settings.yolo_device or "auto").strip()
        predict_kwargs: dict[str, Any] = {
            "verbose": False,
            "imgsz": int(settings.fine_tune_imgsz),
        }
        if device.lower() not in {"", "auto"}:
            predict_kwargs["device"] = device

        try:
            with self._lock:
                results = self._model.predict(source=crop, **predict_kwargs)
            if not results:
                return {"species": "bird", "confidence": 0.0}
            result = results[0]
            probs = getattr(result, "probs", None)
            if probs is None:
                return {"species": "bird", "confidence": 0.0}
            top_index = int(probs.top1)
            confidence = float(probs.top1conf)
            names = getattr(result, "names", None) or getattr(
                self._model, "names", {}
            ) or {}
            if isinstance(names, dict):
                label = names.get(top_index, names.get(str(top_index), "bird"))
            elif isinstance(names, (list, tuple)) and 0 <= top_index < len(names):
                label = names[top_index]
            else:
                label = "bird"
            species = self._display_species(label)

            # Abaixo do limiar, é mais honesto registrar "ave" do que arriscar
            # uma espécie errada na Life List. O observador pode corrigir depois.
            if confidence < float(settings.fine_tune_min_confidence):
                return {
                    "species": "bird",
                    "confidence": confidence,
                    "model_species": species,
                    "below_threshold": True,
                }
            return {
                "species": species,
                "confidence": confidence,
                "model_species": species,
                "fine_tuned": True,
            }
        except Exception:
            logger.exception("Falha na classificação fine-tunada de espécies")
            return {"species": "bird", "confidence": 0.0}


class HookableSpeciesClassifier(SpeciesClassifier):
    """Wrapper que delega a um modelo opcional e cai no passthrough.

    Exemplo de uso futuro::

        classifier = HookableSpeciesClassifier(model=MeuModeloDeAves())
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
        logger.info(
            "Classificador secundário de espécies %s",
            "definido (fine-tunado)" if model else "limpo (padrão)",
        )

    def classify(
        self,
        frame: np.ndarray,
        bbox: tuple[float, float, float, float],
    ) -> SpeciesPrediction:
        if self.model is None:
            return self.fallback.classify(frame, bbox)

        try:
            # API esperada: model.predict(crop) -> (species, confidence) ou dict.
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
                return SpeciesPrediction(
                    species=str(result[0]), confidence=float(result[1])
                )
            if isinstance(result, dict):
                return SpeciesPrediction(
                    species=str(result.get("species", "bird")),
                    confidence=float(result.get("confidence", 0.0)),
                    extras=result,
                )
            return SpeciesPrediction(species=str(result), confidence=0.0)
        except Exception:
            logger.exception("Classificador secundário falhou — usando fallback")
            return self.fallback.classify(frame, bbox)


_default_classifier: HookableSpeciesClassifier | None = None
_default_lock = threading.Lock()


def _build_fine_tuned_model() -> YoloClassificationModel | None:
    """Instancia o modelo treinado quando o artefato existe no disco."""
    model_path = get_settings().fine_tuned_model_path
    if not model_path.is_file():
        return None
    return YoloClassificationModel(model_path)


def get_default_species_classifier() -> SpeciesClassifier:
    """Classificador compartilhado pelo pipeline ao vivo e pela análise offline.

    É um singleton de propósito: quando o fine-tuning termina, o mesmo objeto
    recebe o novo modelo via :func:`reload_default_species_classifier` e todas
    as câmeras passam a usá-lo imediatamente, sem reiniciar o aplicativo.
    """
    global _default_classifier
    if _default_classifier is None:
        with _default_lock:
            if _default_classifier is None:
                _default_classifier = HookableSpeciesClassifier(
                    model=_build_fine_tuned_model()
                )
    return _default_classifier


def reload_default_species_classifier() -> SpeciesClassifier:
    """Recarrega o modelo fine-tunado no classificador compartilhado."""
    model = _build_fine_tuned_model()
    classifier = get_default_species_classifier()
    if isinstance(classifier, HookableSpeciesClassifier):
        classifier.set_model(model)
    return classifier


__all__ = [
    "HookableSpeciesClassifier",
    "PassthroughSpeciesClassifier",
    "SpeciesClassifier",
    "SpeciesPrediction",
    "YoloClassificationModel",
    "get_default_species_classifier",
    "reload_default_species_classifier",
]
