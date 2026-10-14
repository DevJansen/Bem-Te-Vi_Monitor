"""Per-camera vision pipeline: capture → detect → zone → clip → notify."""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np

from app.core.config import get_settings
from app.domain.models import VisitOut, ZoneConfig, ZoneMode
from app.infra.ai.annotate import draw_bird_detections
from app.infra.ai.box_tracker import BoxTracker
from app.infra.ai.detector import BirdDetector, Detection, get_bird_detector
from app.infra.ai.pre_record_buffer import PreRecordBuffer
from app.infra.ai.species_classifier import SpeciesClassifier, get_default_species_classifier
from app.infra.ai.zone_validator import ZoneValidator, point_in_polygon
from app.infra.camera.manager import get_camera_manager
from app.infra.camera.streamer import CameraStreamer, StreamStatus
from app.infra.database.repository import CameraRepository, SettingsRepository, VisitRepository
from app.infra.media.storage import (
    relative_to_captures,
    save_bird_crop,
    save_clip_mp4,
    save_thumbnail,
)

logger = logging.getLogger(__name__)

VisitHandler = Callable[[VisitOut], None]


class CameraPipeline(threading.Thread):
    def __init__(
        self,
        camera_id: str,
        detector: BirdDetector | None = None,
        classifier: SpeciesClassifier | None = None,
        on_visit: VisitHandler | None = None,
    ) -> None:
        super().__init__(name=f"pipeline-{camera_id}", daemon=True)
        self.camera_id = camera_id
        self.settings = get_settings()
        self.detector = detector or get_bird_detector()
        self.classifier = classifier or get_default_species_classifier()
        self.on_visit = on_visit
        self._stop = threading.Event()
        self.camera_repo = CameraRepository(self.settings.db_path)
        self.visit_repo = VisitRepository(self.settings.db_path)
        self.settings_repo = SettingsRepository(self.settings.db_path)
        self.buffer = PreRecordBuffer(seconds=self.settings.pre_record_seconds)
        self.zone_validator = ZoneValidator()
        self._configured_zones: list[ZoneConfig] = []
        self._post_frames_remaining = 0
        self._pending_event: dict[str, Any] | None = None
        self._post_collected: list[np.ndarray] = []
        self._last_detections: list[Detection] = []

    def stop(self) -> None:
        self._stop.set()

    def _load_zones(self) -> None:
        row = self.camera_repo.get(self.camera_id)
        if not row:
            self._configured_zones = []
            self.zone_validator.set_zones([])
            return
        try:
            data = json.loads(row.get("zones_json") or '{"zones":[]}')
            zones = [ZoneConfig.model_validate(z) for z in data.get("zones", [])]
        except Exception:
            logger.exception("Invalid zones for camera %s", self.camera_id)
            zones = []
        self._configured_zones = [zone for zone in zones if zone.enabled]
        self.zone_validator.set_zones(
            [zone for zone in self._configured_zones if zone.mode == ZoneMode.INCLUDE]
        )

    def _confidence_threshold(self) -> float:
        raw = self.settings_repo.get("yolo_confidence")
        if raw is not None:
            try:
                return float(raw)
            except ValueError:
                pass
        return self.settings.yolo_confidence

    def _notify_enabled(self) -> bool:
        raw = self.settings_repo.get("notifications_enabled", "true")
        return str(raw).lower() in {"1", "true", "yes", "on"}

    def _min_confidence_notify(self) -> float:
        raw = self.settings_repo.get("min_confidence_notify")
        if raw is not None:
            try:
                return float(raw)
            except ValueError:
                pass
        return self.settings.yolo_confidence

    def _detect_in_zones(self, frame: np.ndarray) -> list[Detection]:
        """Mascarar áreas inválidas antes do YOLO e filtrar detecções pelo centro."""
        height, width = frame.shape[:2]
        inclusion_zones = [
            zone for zone in self._configured_zones if zone.mode == ZoneMode.INCLUDE
        ]
        exclusion_zones = [
            zone for zone in self._configured_zones if zone.mode == ZoneMode.EXCLUDE
        ]

        mask = np.zeros((height, width), dtype=np.uint8)
        if not inclusion_zones:
            mask.fill(255)
        else:
            for zone in inclusion_zones:
                points = np.array(
                    [
                        [
                            round(point.x * (width - 1)),
                            round(point.y * (height - 1)),
                        ]
                        for point in zone.points
                    ],
                    dtype=np.int32,
                )
                cv2.fillPoly(mask, [points], 255)

        for zone in exclusion_zones:
            points = np.array(
                [
                    [
                        round(point.x * (width - 1)),
                        round(point.y * (height - 1)),
                    ]
                    for point in zone.points
                ],
                dtype=np.int32,
            )
            cv2.fillPoly(mask, [points], 0)

        masked_frame = cv2.bitwise_and(frame, frame, mask=mask)
        detections = self.detector.detect(masked_frame)
        return [
            detection
            for detection in detections
            if self._is_detection_allowed(detection, width, height)
        ]

    def _is_detection_allowed(
        self, detection: Detection, width: int, height: int
    ) -> bool:
        center_x, center_y = detection.normalized_center(width, height)
        inclusion_zones = [
            zone for zone in self._configured_zones if zone.mode == ZoneMode.INCLUDE
        ]
        if inclusion_zones and not any(
            point_in_polygon(
                center_x, center_y, [(point.x, point.y) for point in zone.points]
            )
            for zone in inclusion_zones
        ):
            return False
        return not any(
            point_in_polygon(
                center_x, center_y, [(point.x, point.y) for point in zone.points]
            )
            for zone in self._configured_zones
            if zone.mode == ZoneMode.EXCLUDE
        )

    def _ensure_stream(self) -> CameraStreamer | None:
        manager = get_camera_manager()
        streamer = manager.get_streamer(self.camera_id)
        if streamer is None:
            streamer = manager.upsert_streamer(self.camera_id)
        if streamer is None:
            return None
        if streamer.status != StreamStatus.ONLINE:
            streamer.open()
        return streamer

    def _handle_trigger(
        self,
        frame: np.ndarray,
        detection: Detection,
        trigger_zone_id: str,
        dwell: float,
        pre_frames: list[np.ndarray],
        fps: float,
    ) -> None:
        visit_id = str(uuid.uuid4())
        species_pred = self.classifier.classify(frame, detection.bbox)
        species = species_pred.species
        conf = float(detection.confidence)

        thumb = save_thumbnail(frame, self.camera_id, visit_id)
        crop_path = save_bird_crop(frame, detection.bbox, visit_id)
        post_sec = float(
            self.settings_repo.get("post_record_seconds")
            or self.settings.post_record_seconds
        )
        self._pending_event = {
            "visit_id": visit_id,
            "species": species,
            "confidence": conf,
            "detection": detection,
            "zone_id": trigger_zone_id,
            "dwell": dwell,
            "pre_frames": pre_frames,
            "thumb": thumb,
            "crop_path": crop_path,
            "fps": fps,
            "species_extras": species_pred.extras or {},
        }
        self._post_frames_remaining = max(int(post_sec * fps), 0)
        self._post_collected = []
        if self._post_frames_remaining == 0:
            self._finalize_visit()

    def _finalize_visit(self) -> None:
        event = self._pending_event
        self._pending_event = None
        if event is None:
            return

        frames = list(event["pre_frames"]) + list(self._post_collected)
        self._post_collected = []
        clip_path = save_clip_mp4(
            frames,
            self.camera_id,
            event["visit_id"],
            event["fps"],
        )
        detected_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        thumb: Path | None = event.get("thumb")
        clip_rel = relative_to_captures(clip_path) if clip_path else None
        thumb_rel = relative_to_captures(thumb) if thumb else None

        try:
            visit = self.visit_repo.create(
                visit_id=event["visit_id"],
                camera_id=self.camera_id,
                species=event["species"],
                confidence=float(event["confidence"]),
                detected_at=detected_at,
                dwell_seconds=float(event["dwell"]),
                clip_path=clip_rel,
                thumbnail_path=thumb_rel,
                bbox=event["detection"].as_list(),
                zone_id=event["zone_id"],
                metadata={
                    "class_name": event["detection"].class_name,
                    "species_extras": event.get("species_extras") or {},
                    "crop_path": event.get("crop_path"),
                },
            )
        except Exception:
            logger.exception("Failed to persist visit for camera %s", self.camera_id)
            return

        visit_out = self.visit_repo.to_out(visit)

        if self.on_visit and self._notify_enabled():
            if visit_out.confidence >= self._min_confidence_notify():
                try:
                    self.on_visit(visit_out)
                except Exception:
                    logger.exception("on_visit callback failed")

    def run(self) -> None:
        logger.info("Pipeline started for camera %s", self.camera_id)
        if not self.detector.load():
            logger.error(
                "Detector unavailable for camera %s: %s",
                self.camera_id,
                self.detector.load_error,
            )

        self._load_zones()
        infer_every_n = 4
        frame_idx = 0
        last_zone_reload = 0.0
        detections: list[Detection] = []
        tracker = BoxTracker()

        while not self._stop.is_set():
            try:
                if time.time() - last_zone_reload > 15:
                    self._load_zones()
                    last_zone_reload = time.time()

                streamer = self._ensure_stream()
                if streamer is None:
                    time.sleep(1.0)
                    continue

                ok, frame = streamer.read()
                if not ok or frame is None:
                    streamer.reconnect()
                    continue

                fps = streamer.fps
                self.buffer.configure(
                    seconds=float(
                        self.settings_repo.get("pre_record_seconds")
                        or self.settings.pre_record_seconds
                    ),
                    fps=fps,
                )
                self.buffer.push(frame)
                frame_idx += 1

                if self._post_frames_remaining > 0:
                    self._post_collected.append(frame.copy())
                    self._post_frames_remaining -= 1
                    if self._post_frames_remaining <= 0:
                        self._finalize_visit()

                if frame_idx % infer_every_n == 0:
                    self.detector.confidence = min(
                        1.0,
                        max(0.60, self._confidence_threshold()),
                    )
                    detections = self._detect_in_zones(frame)
                    tracker.reset(frame, detections)
                else:
                    detections = tracker.update(frame)

                h, w = frame.shape[:2]
                detections = [
                    detection
                    for detection in detections
                    if self._is_detection_allowed(detection, w, h)
                ]
                centers = [d.normalized_center(w, h) for d in detections]
                triggers = self.zone_validator.update(centers)
                if triggers and detections and self._pending_event is None:
                    trigger = triggers[0]
                    trigger_zone = next(
                        (
                            zone
                            for zone in self.zone_validator.zones
                            if zone.id == trigger.zone_id
                        ),
                        None,
                    )
                    eligible = [
                        detection
                        for detection in detections
                        if trigger_zone is None
                        or point_in_polygon(
                            *detection.normalized_center(w, h),
                            [(point.x, point.y) for point in trigger_zone.points],
                        )
                    ]
                    if eligible:
                        best = max(eligible, key=lambda d: d.confidence)
                        pre = self.buffer.snapshot(
                            include_seconds=3.0,
                            exclude_latest=True,
                        )
                        self._handle_trigger(
                            frame=frame,
                            detection=best,
                            trigger_zone_id=trigger.zone_id,
                            dwell=trigger.dwell_seconds,
                            pre_frames=pre,
                            fps=self.buffer.estimated_fps(),
                        )

                streamer.set_annotated_frame(
                    draw_bird_detections(
                        frame,
                        detections,
                        min_confidence=self.detector.confidence,
                    )
                )

            except Exception:
                logger.exception("Pipeline loop error camera=%s", self.camera_id)
                time.sleep(0.5)

        if self._pending_event is not None:
            try:
                self._finalize_visit()
            except Exception:
                logger.exception("Failed to finalize pending visit on stop")

        logger.info("Pipeline stopped for camera %s", self.camera_id)


class PipelineSupervisor:
    """Starts/stops per-camera pipelines."""

    def __init__(self) -> None:
        self._pipelines: dict[str, CameraPipeline] = {}
        self._lock = threading.RLock()
        self._on_visit: VisitHandler | None = None

    def set_visit_handler(self, handler: VisitHandler) -> None:
        self._on_visit = handler

    def start_camera(self, camera_id: str) -> None:
        with self._lock:
            existing = self._pipelines.get(camera_id)
            if existing and existing.is_alive():
                return
            pipeline = CameraPipeline(camera_id, on_visit=self._on_visit)
            self._pipelines[camera_id] = pipeline
            pipeline.start()

    def stop_camera(self, camera_id: str) -> None:
        with self._lock:
            pipeline = self._pipelines.pop(camera_id, None)
        if pipeline is not None:
            pipeline.stop()
            pipeline.join(timeout=5.0)
        get_camera_manager().remove_streamer(camera_id)

    def restart_camera(self, camera_id: str) -> None:
        self.stop_camera(camera_id)
        row = CameraRepository(get_settings().db_path).get(camera_id)
        if row and row["enabled"]:
            self.start_camera(camera_id)

    def sync_from_db(self) -> None:
        settings = get_settings()
        repo = CameraRepository(settings.db_path)
        enabled_ids = {row["id"] for row in repo.list_all() if row["enabled"]}
        with self._lock:
            running = set(self._pipelines.keys())
        for camera_id in running - enabled_ids:
            self.stop_camera(camera_id)
        for camera_id in enabled_ids:
            with self._lock:
                pipeline = self._pipelines.get(camera_id)
                alive = pipeline is not None and pipeline.is_alive()
            if not alive:
                self.start_camera(camera_id)

    def shutdown(self) -> None:
        with self._lock:
            ids = list(self._pipelines.keys())
        for camera_id in ids:
            self.stop_camera(camera_id)


_supervisor: PipelineSupervisor | None = None
_supervisor_lock = threading.Lock()


def get_pipeline_supervisor() -> PipelineSupervisor:
    global _supervisor
    with _supervisor_lock:
        if _supervisor is None:
            _supervisor = PipelineSupervisor()
        return _supervisor
