"""Lightweight optical-flow tracking between YOLO inference frames."""

from __future__ import annotations

import cv2
import numpy as np

from app.infra.ai.detector import Detection


class BoxTracker:
    """Tracks detected box positions with sparse Lucas-Kanade optical flow."""

    def __init__(self) -> None:
        self._gray: np.ndarray | None = None
        self._detections: list[Detection] = []

    def reset(self, frame: np.ndarray, detections: list[Detection]) -> None:
        self._gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self._detections = list(detections)

    def update(self, frame: np.ndarray) -> list[Detection]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if self._gray is None or not self._detections:
            self._gray = gray
            self._detections = []
            return []

        tracked: list[Detection] = []
        for detection in self._detections:
            x1, y1, x2, y2 = detection.bbox
            width, height = x2 - x1, y2 - y1
            if width < 2 or height < 2:
                continue

            points = np.array(
                [
                    [x1 + width * 0.2, y1 + height * 0.2],
                    [x1 + width * 0.8, y1 + height * 0.2],
                    [x1 + width * 0.2, y1 + height * 0.8],
                    [x1 + width * 0.8, y1 + height * 0.8],
                    [x1 + width * 0.5, y1 + height * 0.5],
                ],
                dtype=np.float32,
            ).reshape(-1, 1, 2)
            next_points, status, _ = cv2.calcOpticalFlowPyrLK(
                self._gray,
                gray,
                points,
                None,
                winSize=(15, 15),
                maxLevel=2,
            )
            if next_points is None or status is None:
                continue

            valid = status.reshape(-1).astype(bool)
            if np.count_nonzero(valid) < 3:
                continue
            displacement = np.median(
                (next_points.reshape(-1, 2) - points.reshape(-1, 2))[valid],
                axis=0,
            )
            nx1 = max(0.0, min(float(frame.shape[1] - 1), x1 + float(displacement[0])))
            ny1 = max(0.0, min(float(frame.shape[0] - 1), y1 + float(displacement[1])))
            nx2 = max(0.0, min(float(frame.shape[1] - 1), x2 + float(displacement[0])))
            ny2 = max(0.0, min(float(frame.shape[0] - 1), y2 + float(displacement[1])))
            if nx2 <= nx1 or ny2 <= ny1:
                continue

            tracked.append(
                Detection(
                    class_id=detection.class_id,
                    class_name=detection.class_name,
                    confidence=detection.confidence,
                    bbox=(nx1, ny1, nx2, ny2),
                )
            )

        self._gray = gray
        self._detections = tracked
        return list(tracked)
