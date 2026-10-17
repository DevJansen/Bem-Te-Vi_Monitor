"""Registro thread-safe de estatísticas por stream (Alaris Core distribuído).

Cada câmera ativa mantém seu próprio estado em tempo real (status de conexão,
FPS, backend de inferência, aves ativas no comedouro, pico de indivíduos e
inferências). O ``CameraPipeline`` publica esses dados a cada ciclo e a API/
painel os consome — é o que alimenta os selos "Alaris Core" no grid multi-câmera.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class StreamStats:
    """Estado em tempo real de um stream/câmera."""

    camera_id: str
    name: str = ""
    # idle | connecting | online | reconnecting | error | stopped
    status: str = "idle"
    fps: float = 0.0
    # Backend de inferência do Alaris neste fluxo (tensorrt | onnx | pytorch).
    backend: str | None = None
    # Aves ativas no comedouro/bebedouro neste instante.
    active_birds: int = 0
    # Pico simultâneo observado na janela atual.
    individuals_peak: int = 0
    # Inferências executadas neste fluxo desde o início.
    inferences: int = 0
    last_error: str | None = None
    updated_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class StreamRegistry:
    """Mantém o estado em tempo real de cada stream/câmera ativa."""

    def __init__(self) -> None:
        self._stats: dict[str, StreamStats] = {}
        self._lock = threading.Lock()

    def update(self, camera_id: str, **campos: Any) -> None:
        """Atualiza (parcialmente) o estado de um stream."""
        with self._lock:
            stats = self._stats.get(camera_id)
            if stats is None:
                stats = StreamStats(camera_id=camera_id)
                self._stats[camera_id] = stats
            for chave, valor in campos.items():
                if hasattr(stats, chave):
                    setattr(stats, chave, valor)
            stats.updated_at = time.time()

    def get(self, camera_id: str) -> StreamStats | None:
        with self._lock:
            stats = self._stats.get(camera_id)
            return StreamStats(**asdict(stats)) if stats is not None else None

    def all(self) -> list[StreamStats]:
        with self._lock:
            return [StreamStats(**asdict(stats)) for stats in self._stats.values()]

    def remove(self, camera_id: str) -> None:
        with self._lock:
            self._stats.pop(camera_id, None)

    def clear(self) -> None:
        with self._lock:
            self._stats.clear()


_registry: StreamRegistry | None = None
_registry_lock = threading.Lock()


def get_stream_registry() -> StreamRegistry:
    """Instância global (singleton) do registro de streams."""
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = StreamRegistry()
        return _registry
