"""Log cognitivo da IA — os "pensamentos" do motor em tempo real.

Registra, em memória, os eventos de raciocínio do pipeline (detecção, seleção do
melhor quadro, identificação de espécie, auto-calibração por clima, anomalias…).
É um buffer circular (ring buffer) thread-safe, consultável de forma incremental
pelo painel via ``GET /api/ai/logs`` — dando a sensação de "assistir a IA pensar".

Não persiste em disco de propósito: é telemetria de tempo real, barata e volátil.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Níveis aceitos (orientam a cor/ícone no painel).
NIVEL_INFO = "info"
NIVEL_ANALISE = "analise"
NIVEL_SUCESSO = "sucesso"
NIVEL_ATENCAO = "atencao"
NIVEL_ALERTA = "alerta"

NIVEIS_VALIDOS = {
    NIVEL_INFO,
    NIVEL_ANALISE,
    NIVEL_SUCESSO,
    NIVEL_ATENCAO,
    NIVEL_ALERTA,
}

# Capacidade padrão do buffer (últimos eventos mantidos em memória).
CAPACIDADE_PADRAO = 400


@dataclass(frozen=True)
class EventoCognitivo:
    """Um "pensamento" da IA, com hora, nível e dados estruturados."""

    id: int
    timestamp: float
    hora: str
    nivel: str
    origem: str | None
    mensagem: str
    dados: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "hora": self.hora,
            "nivel": self.nivel,
            "origem": self.origem,
            "mensagem": self.mensagem,
            "dados": self.dados,
        }


class CognitiveLog:
    """Buffer circular thread-safe dos eventos cognitivos da IA."""

    def __init__(self, capacidade: int = CAPACIDADE_PADRAO) -> None:
        self._eventos: deque[EventoCognitivo] = deque(maxlen=max(1, int(capacidade)))
        self._seq = 0
        self._lock = threading.Lock()

    def registrar(
        self,
        mensagem: str,
        *,
        nivel: str = NIVEL_INFO,
        origem: str | None = None,
        **dados: Any,
    ) -> EventoCognitivo:
        """Adiciona um evento ao log e devolve-o.

        ``origem`` costuma ser o id/nome da câmera. ``dados`` são pares
        chave/valor arbitrários (ex.: ``confianca=0.94``, ``especie="Cambacica"``).
        """
        texto = str(mensagem or "").strip()
        if not texto:
            texto = "—"
        nivel_final = nivel if nivel in NIVEIS_VALIDOS else NIVEL_INFO
        agora = time.time()
        with self._lock:
            self._seq += 1
            evento = EventoCognitivo(
                id=self._seq,
                timestamp=agora,
                hora=datetime.fromtimestamp(agora).strftime("%H:%M:%S"),
                nivel=nivel_final,
                origem=origem,
                mensagem=texto,
                dados=dict(dados),
            )
            self._eventos.append(evento)
            return evento

    def listar(
        self, *, limit: int = 50, since_id: int | None = None
    ) -> list[EventoCognitivo]:
        """Devolve os eventos mais recentes (ordem cronológica).

        Com ``since_id``, devolve apenas os eventos **mais novos** que ele —
        ideal para o painel buscar somente o que apareceu desde a última consulta.
        """
        with self._lock:
            eventos = list(self._eventos)
        if since_id is not None:
            eventos = [evento for evento in eventos if evento.id > int(since_id)]
        limite = max(1, int(limit))
        return eventos[-limite:]

    def ultimo_id(self) -> int:
        with self._lock:
            return self._seq

    def limpar(self) -> None:
        with self._lock:
            self._eventos.clear()


_log: CognitiveLog | None = None
_log_lock = threading.Lock()


def get_cognitive_log() -> CognitiveLog:
    """Instância global (singleton) do log cognitivo."""
    global _log
    with _log_lock:
        if _log is None:
            _log = CognitiveLog()
        return _log


def registrar_pensamento(
    mensagem: str,
    *,
    nivel: str = NIVEL_INFO,
    origem: str | None = None,
    **dados: Any,
) -> None:
    """Atalho tolerante a falhas para registrar um pensamento da IA."""
    try:
        get_cognitive_log().registrar(
            mensagem, nivel=nivel, origem=origem, **dados
        )
    except Exception:  # pragma: no cover — telemetria nunca derruba o pipeline
        pass
