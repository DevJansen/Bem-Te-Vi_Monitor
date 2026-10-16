"""Telemetria do motor de IA local (Edge AI) — visível no painel "AI Core".

Acumula, em memória e de forma thread-safe, as métricas que evidenciam a IA
trabalhando em tempo real:

- **Throughput:** FPS do pipeline, nº de inferências (hoje e total) e detecções.
- **Desempenho:** latência da inferência (última, média, mínima, máxima e p95).
- **Recursos:** uso de CPU e memória do processo/sistema (via ``psutil``).
- **Modelo:** nome, backend (TensorRT/ONNX/PyTorch), dispositivo e resolução.

É tudo leitura barata e volátil (sem disco). O endpoint ``GET /api/ai/status``
serve este retrato para o widget futurista do Dashboard.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import date
from typing import Any

# Quantas amostras de latência manter para as estatísticas móveis.
_JANELA_LATENCIA = 240

# Estados possíveis do motor, exibidos no painel.
ESTADO_OCIOSO = "Aguardando stream"
ESTADO_ANALISANDO = "Analisando frame"
ESTADO_CARREGANDO = "Carregando modelo"
ESTADO_INDISPONIVEL = "Indisponível"


def _percentil(valores: list[float], p: float) -> float:
    """Percentil simples (interpolação linear) de uma lista de floats."""
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return ordenados[0]
    posicao = (len(ordenados) - 1) * max(0.0, min(1.0, p))
    inferior = int(posicao)
    superior = min(inferior + 1, len(ordenados) - 1)
    fracao = posicao - inferior
    return ordenados[inferior] * (1 - fracao) + ordenados[superior] * fracao


class AiTelemetry:
    """Coletor central de métricas do motor de IA (singleton)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._iniciado_em = time.time()
        self._dia = date.today()
        # Contadores acumulados.
        self._inferencias_total = 0
        self._inferencias_hoje = 0
        self._deteccoes_total = 0
        self._deteccoes_hoje = 0
        self._quadros_analisados = 0
        # Latências recentes (ms).
        self._latencia: deque[float] = deque(maxlen=_JANELA_LATENCIA)
        self._latencia_ultima = 0.0
        # Estado do motor e throughput.
        self._fps = 0.0
        self._estado = ESTADO_CARREGANDO
        # Informações do modelo carregado.
        self._modelo: dict[str, Any] = {}
        # Recursos (psutil é opcional: degrada com elegância se ausente).
        self._psutil = None
        self._processo = None
        try:  # pragma: no cover — depende do ambiente
            import psutil

            self._psutil = psutil
            self._processo = psutil.Process()
        except Exception:
            self._psutil = None

    # ------------------------------------------------------------------ #
    # Registro de eventos
    # ------------------------------------------------------------------ #
    def _virar_dia_se_preciso(self) -> None:
        """Zera os contadores "de hoje" quando o dia muda."""
        hoje = date.today()
        if hoje != self._dia:
            self._dia = hoje
            self._inferencias_hoje = 0
            self._deteccoes_hoje = 0

    def registrar_modelo(
        self,
        *,
        model: str,
        backend: str | None,
        device: str | None,
        imgsz: int | None,
        notes: list[str] | None = None,
    ) -> None:
        with self._lock:
            self._modelo = {
                "model": model,
                "backend": backend or "pytorch",
                "device": device or "cpu",
                "imgsz": int(imgsz) if imgsz else None,
                "notes": list(notes or []),
            }
            self._estado = ESTADO_OCIOSO

    def registrar_inferencia(self, latencia_ms: float, deteccoes: int = 0) -> None:
        """Registra uma inferência concluída (latência em ms e nº de detecções)."""
        valor = max(0.0, float(latencia_ms))
        with self._lock:
            self._virar_dia_se_preciso()
            self._inferencias_total += 1
            self._inferencias_hoje += 1
            self._quadros_analisados += 1
            self._deteccoes_total += max(0, int(deteccoes))
            self._deteccoes_hoje += max(0, int(deteccoes))
            self._latencia.append(valor)
            self._latencia_ultima = valor

    def definir_fps(self, fps: float) -> None:
        with self._lock:
            if fps and fps > 0:
                self._fps = round(float(fps), 1)

    def definir_estado(self, estado: str) -> None:
        with self._lock:
            self._estado = str(estado)

    def registrar_quadro(self, quantidade: int = 1) -> None:
        """Conta quadros processados pelo pipeline (throughput visual)."""
        with self._lock:
            self._quadros_analisados += max(0, int(quantidade))

    # ------------------------------------------------------------------ #
    # Leitura
    # ------------------------------------------------------------------ #
    def _recursos(self) -> dict[str, Any]:
        """Uso de recursos do processo/sistema (ou nulos se indisponível)."""
        if self._psutil is None or self._processo is None:
            return {
                "cpu_percent": None,
                "memory_mb": None,
                "memory_percent": None,
                "system_cpu_percent": None,
            }
        try:
            memoria = self._processo.memory_info()
            memoria_sistema = self._psutil.virtual_memory()
            return {
                # cpu_percent(None) mede desde a chamada anterior (não bloqueia).
                "cpu_percent": round(self._processo.cpu_percent(None), 1),
                "memory_mb": round(memoria.rss / (1024 * 1024), 1),
                "memory_percent": round(
                    memoria.rss / max(memoria_sistema.total, 1) * 100, 1
                ),
                "system_cpu_percent": round(
                    self._psutil.cpu_percent(None), 1
                ),
            }
        except Exception:
            return {
                "cpu_percent": None,
                "memory_mb": None,
                "memory_percent": None,
                "system_cpu_percent": None,
            }

    def snapshot(self) -> dict[str, Any]:
        """Retrato completo das métricas para o endpoint de status."""
        with self._lock:
            self._virar_dia_se_preciso()
            latencias = list(self._latencia)
            dados = {
                "state": self._estado,
                "started_at": self._iniciado_em,
                "uptime_seconds": round(time.time() - self._iniciado_em, 1),
                "model": dict(self._modelo),
                "throughput": {
                    "fps": self._fps,
                    "inferences_today": self._inferencias_hoje,
                    "inferences_total": self._inferencias_total,
                    "detections_today": self._deteccoes_hoje,
                    "detections_total": self._deteccoes_total,
                    "frames_analyzed": self._quadros_analisados,
                },
                "performance": {
                    "latency_ms_last": round(self._latencia_ultima, 1),
                    "latency_ms_avg": round(
                        sum(latencias) / len(latencias), 1
                    )
                    if latencias
                    else 0.0,
                    "latency_ms_min": round(min(latencias), 1) if latencias else 0.0,
                    "latency_ms_max": round(max(latencias), 1) if latencias else 0.0,
                    "latency_ms_p95": round(_percentil(latencias, 0.95), 1),
                    "samples": len(latencias),
                },
            }
        dados["resources"] = self._recursos()
        return dados


_telemetria: AiTelemetry | None = None
_telemetria_lock = threading.Lock()


def get_ai_telemetry() -> AiTelemetry:
    """Instância global (singleton) da telemetria do motor de IA."""
    global _telemetria
    with _telemetria_lock:
        if _telemetria is None:
            _telemetria = AiTelemetry()
        return _telemetria
