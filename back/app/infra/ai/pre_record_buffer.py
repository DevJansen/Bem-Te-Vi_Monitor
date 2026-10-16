"""Buffer circular de pré-gravação (3 segundos anteriores) com ``deque``.

Mantém em RAM os quadros mais recentes da câmera para que, quando o YOLOv8
confirmar uma ave, o clipe comece *antes* do pouso — o "pré-roll" de 3 s.

Segurança de threads: o buffer é escrito pelo laço de captura e lido no momento
do gatilho (e potencialmente por rotinas de manutenção). Todo acesso passa por
um ``RLock`` reentrante, garantindo que um *snapshot* nunca veja um deque em
mutação. Cada quadro é copiado no ``push`` para que o chamador possa reutilizar
o seu buffer sem afetar o histórico.
"""

from __future__ import annotations

import threading
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
        self._lock = threading.RLock()
        self.seconds = max(3.0, float(seconds))
        self.target_fps = max(1.0, float(target_fps))
        self._maxlen = max(int(self.seconds * self.target_fps) + 5, 10)
        self._frames: deque[BufferedFrame] = deque(maxlen=self._maxlen)

    def configure(self, seconds: float | None = None, fps: float | None = None) -> None:
        """Ajusta a janela (segundos) e o FPS estimado do buffer.

        É chamado a cada quadro do pipeline, então sai cedo quando nada mudou —
        antes, cada chamada reconstruía o ``deque`` inteiro (custo O(n) por
        quadro). Só reconstrói quando a capacidade realmente muda.
        """
        novo_seconds = self.seconds if seconds is None else max(3.0, float(seconds))
        novo_fps = self.target_fps if fps is None else max(1.0, float(fps))
        novo_maxlen = max(int(novo_seconds * novo_fps) + 5, 10)
        with self._lock:
            if (
                abs(novo_seconds - self.seconds) < 1e-3
                and abs(novo_fps - self.target_fps) < 1e-3
                and novo_maxlen == self._maxlen
            ):
                return
            self.seconds = novo_seconds
            self.target_fps = novo_fps
            self._maxlen = novo_maxlen
            # Reconstrói o deque com a nova capacidade, mantendo os mais novos.
            existentes = list(self._frames)
            self._frames = deque(existentes[-self._maxlen :], maxlen=self._maxlen)

    def push(self, frame: np.ndarray, timestamp: float | None = None) -> None:
        if frame is None:
            return
        ts = time.time() if timestamp is None else timestamp
        # Copia para que o chamador possa mutar o próprio quadro com segurança.
        with self._lock:
            self._frames.append(BufferedFrame(timestamp=ts, frame=frame.copy()))

    def clear(self) -> None:
        with self._lock:
            self._frames.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._frames)

    def frames_since(self, start_ts: float) -> list[np.ndarray]:
        with self._lock:
            return [bf.frame for bf in self._frames if bf.timestamp >= start_ts]

    def snapshot(
        self,
        include_seconds: float | None = None,
        *,
        exclude_latest: bool = False,
    ) -> list[np.ndarray]:
        """Return frames covering the last `include_seconds` (default: buffer window)."""
        with self._lock:
            if not self._frames:
                return []
            frames = list(self._frames)
            if exclude_latest:
                frames = frames[:-1]
            if not frames:
                return []
            window = (
                self.seconds if include_seconds is None else max(0.0, include_seconds)
            )
            cutoff = frames[-1].timestamp - window
            return [bf.frame for bf in frames if bf.timestamp >= cutoff]

    def estimated_fps(self) -> float:
        with self._lock:
            if len(self._frames) < 2:
                return self.target_fps
            dt = self._frames[-1].timestamp - self._frames[0].timestamp
            if dt <= 0:
                return self.target_fps
            return max(len(self._frames) / dt, 1.0)
