"""Agendamento Inteligente e Economia de Recursos (Smart Scheduling).

O Bem-Te-Vi Core ajusta a carga do motor de IA conforme o horário local da câmera:

* **Horários de pico** (manhã e tardinha): análise em plena capacidade.
* **Madrugada/silêncio absoluto**: reduz a taxa de frames ou pausa a análise
  pesada (quando não há visão noturna ativa), preservando CPU/GPU sem perder
  a vigilância dos horários de maior atividade.

A decisão é tomada por câmera, respeitando o fuso horário local do jardim.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app.core.config import get_settings
from app.infra.database.repository import CameraRepository, SettingsRepository

logger = logging.getLogger(__name__)


class ModoVarredura(str, Enum):
    """Modo de varredura do Bem-Te-Vi Core."""

    PLENO = "pleno"            # análise em capacidade total
    ECONOMIA = "economia"      # taxa de frames reduzida
    PAUSA = "pausa"            # análise pesada pausada (só detecção leve)


# Faixas de horário (hora local da câmera) consideradas de pico de atividade.
_HORARIOS_PICO = {5, 6, 7, 8, 9, 16, 17, 18, 19}
# Horário a partir do qual a madrugada entra em silêncio absoluto.
_MADRUGADA_INICIO = 23
_MADRUGADA_FIM = 4


@dataclass(frozen=True)
class DecisaoAgendamento:
    """Decisão do agendamento inteligente para uma câmera."""

    camera_id: str
    modo: ModoVarredura
    hora_local: int
    frame_stride: int
    motivo: str


class SmartScheduler:
    """Gerenciador de carga do motor de IA por câmera e horário."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.camera_repo = CameraRepository(self.settings.db_path)
        self.settings_repo = SettingsRepository(self.settings.db_path)

    def _agendamento_habilitado(self) -> bool:
        raw = self.settings_repo.get("smart_scheduling_enabled", "true")
        return str(raw).lower() in {"1", "true", "yes", "on"}

    def _visao_noturna_ativa(self, camera_id: str) -> bool:
        """Indica se a câmera tem visão noturna ativa (não pausa à noite)."""
        row = self.camera_repo.get(camera_id)
        if row is None:
            return False
        # A visão noturna é global; consultamos a configuração.
        return self.settings.night_vision_mode in {"on", "auto"}

    def _hora_local(self, camera_id: str) -> int:
        """Hora local da câmera (fuso cadastrado) ou UTC como fallback."""
        row = self.camera_repo.get(camera_id)
        tz_name = (row or {}).get("timezone")
        if tz_name:
            try:
                from zoneinfo import ZoneInfo

                return datetime.now(ZoneInfo(tz_name)).hour
            except Exception:
                logger.debug("Fuso inválido para câmera %s: %s", camera_id, tz_name)
        return datetime.now(timezone.utc).hour

    def decidir(self, camera_id: str) -> DecisaoAgendamento:
        """Decide o modo de varredura para a câmera no instante atual."""
        hora = self._hora_local(camera_id)

        if not self._agendamento_habilitado():
            return DecisaoAgendamento(
                camera_id=camera_id,
                modo=ModoVarredura.PLENO,
                hora_local=hora,
                frame_stride=1,
                motivo="Agendamento inteligente desativado.",
            )

        # Horário de pico: capacidade total.
        if hora in _HORARIOS_PICO:
            return DecisaoAgendamento(
                camera_id=camera_id,
                modo=ModoVarredura.PLENO,
                hora_local=hora,
                frame_stride=1,
                motivo="Horário de pico de atividade.",
            )

        # Madrugada sem visão noturna: pausa a análise pesada.
        em_madrugada = hora >= _MADRUGADA_INICIO or hora <= _MADRUGADA_FIM
        if em_madrugada and not self._visao_noturna_ativa(camera_id):
            return DecisaoAgendamento(
                camera_id=camera_id,
                modo=ModoVarredura.PAUSA,
                hora_local=hora,
                frame_stride=4,
                motivo="Madrugada (silêncio absoluto) sem visão noturna.",
            )

        # Fora do pico: economia moderada.
        return DecisaoAgendamento(
            camera_id=camera_id,
            modo=ModoVarredura.ECONOMIA,
            hora_local=hora,
            frame_stride=2,
            motivo="Fora do horário de pico.",
        )

    def aplicar(self, camera_id: str) -> DecisaoAgendamento:
        """Calcula e registra a decisão (para telemetria)."""
        decisao = self.decidir(camera_id)
        logger.debug(
            "Smart Scheduling câmera=%s modo=%s stride=%d motivo=%s",
            camera_id,
            decisao.modo.value,
            decisao.frame_stride,
            decisao.motivo,
        )
        return decisao


_scheduler: SmartScheduler | None = None
_scheduler_lock = __import__("threading").Lock()


def get_smart_scheduler() -> SmartScheduler:
    """Singleton do agendador inteligente."""
    global _scheduler
    with _scheduler_lock:
        if _scheduler is None:
            _scheduler = SmartScheduler()
        return _scheduler
