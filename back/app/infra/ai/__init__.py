"""AI inference adapters (Ultralytics / YOLO)."""

from app.infra.ai.detector import BirdDetector, Detection, get_bird_detector
from app.infra.ai.pipeline import CameraPipeline, PipelineSupervisor, get_pipeline_supervisor
from app.infra.ai.pre_record_buffer import PreRecordBuffer
from app.infra.ai.species_classifier import (
    HookableSpeciesClassifier,
    PassthroughSpeciesClassifier,
    SpeciesClassifier,
    SpeciesPrediction,
    get_default_species_classifier,
)
from app.infra.ai.zone_validator import ZoneTrigger, ZoneValidator, point_in_polygon

__all__ = [
    "BirdDetector",
    "CameraPipeline",
    "Detection",
    "HookableSpeciesClassifier",
    "PassthroughSpeciesClassifier",
    "PipelineSupervisor",
    "PreRecordBuffer",
    "SpeciesClassifier",
    "SpeciesPrediction",
    "ZoneTrigger",
    "ZoneValidator",
    "get_bird_detector",
    "get_default_species_classifier",
    "get_pipeline_supervisor",
    "point_in_polygon",
]
