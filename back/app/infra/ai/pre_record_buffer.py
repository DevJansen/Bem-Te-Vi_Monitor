"""Circular pre-recording buffer using collections.deque."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass
class BufferedFrame:
    timestamp: float
    frame: np.ndarray


class PreRecordBuffer:
    """
    Keeps at least three seconds of recent frames for clip export.
    """

    def __init__(self, seconds: float = 3.0, target_fps: float = 15.0) -> None:
        self.seconds = max(3.0, float(seconds))
        self.target_fps = max(1.0, float(target_fps))
        self._maxlen = max(int(self.seconds * self.target_fps) + 5, 10)
        self._frames: deque[BufferedFrame] = deque(maxlen=self._maxlen)

    def configure(self, seconds: float | None = None, fps: float | None = None) -> None:
        if seconds is not None:
            self.seconds = max(3.0, float(seconds))
        if fps is not None:
            self.target_fps = max(1.0, float(fps))
        self._maxlen = max(int(self.seconds * self.target_fps) + 5, 10)
        # Rebuild deque with new maxlen, keeping newest frames
        existing = list(self._frames)
        self._frames = deque(existing[-self._maxlen :], maxlen=self._maxlen)

    def push(self, frame: np.ndarray, timestamp: float | None = None) -> None:
        if frame is None:
            return
        ts = time.time() if timestamp is None else timestamp
        # Copy so callers can mutate their frame safely
        self._frames.append(BufferedFrame(timestamp=ts, frame=frame.copy()))

    def clear(self) -> None:
        self._frames.clear()

    def __len__(self) -> int:
        return len(self._frames)

    def frames_since(self, start_ts: float) -> list[np.ndarray]:
        return [bf.frame for bf in self._frames if bf.timestamp >= start_ts]

    def snapshot(
        self,
        include_seconds: float | None = None,
        *,
        exclude_latest: bool = False,
    ) -> list[np.ndarray]:
        """Return frames covering the last `include_seconds` (default: buffer window)."""
        if not self._frames:
            return []
        frames = list(self._frames)
        if exclude_latest:
            frames = frames[:-1]
        if not frames:
            return []
        window = self.seconds if include_seconds is None else max(0.0, include_seconds)
        cutoff = frames[-1].timestamp - window
        return [bf.frame for bf in frames if bf.timestamp >= cutoff]

    def estimated_fps(self) -> float:
        if len(self._frames) < 2:
            return self.target_fps
        dt = self._frames[-1].timestamp - self._frames[0].timestamp
        if dt <= 0:
            return self.target_fps
        return max(len(self._frames) / dt, 1.0)
