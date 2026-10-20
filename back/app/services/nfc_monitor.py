"""Escuta Noturna de Migração (NFC — Nocturnal Flight Calls).

Módulo que intensifica a escuta do BirdNET durante a janela noturna configurada
(padrão 22:00–05:00 no horário local da câmera). À noite, aves migrantes que
cruzam o céu emitem **chamados de voo curtos** (*flight calls*) — muitas vezes
fracos, rápidos e distantes. Para capturá-los o Bem-Ti-Vi:

* reduz o limiar de confiança do BirdNET dentro da janela;
* marca cada detecção feita à noite com ``is_nfc = 1``, a pontuação ``nfc_score``
  e a data da janela noturna (``night_date``) — assim a aba **Viajantes
  Noturnos (Migração)** filtra apenas esses registros;
* registra um evento global quando o modo é ligado/desligado (transição de
  dia ↔ noite), sem duplicar em sequência.

A janela usa o **fuso horário da câmera** quando disponível (caso contrário, o
fuso local do servidor). Ela atravessa a meia-noite (22:00 → 05:00).
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class NfcMonitor:
    """Monitor singleton de Escuta Noturna de Migração.

    O serviço consulta a janela noturna com base na hora **local da câmera** e
    decide o limiar de confiança efetivo a cada bloco de áudio. O registro de
    transição é feito uma única vez por mudança de estado (dia ↔ noite).
    """

    _instance: NfcMonitor | None = None
    _lock = threading.Lock()

    def __new__(cls) -> NfcMonitor:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._last_nfc_active: bool | None = None

    # ------------------------------------------------------------------
    # Janela noturna
    # ------------------------------------------------------------------
    @staticmethod
    def _zone(timezone_name: str | None) -> ZoneInfo | None:
        try:
            return ZoneInfo(timezone_name) if timezone_name else None
        except Exception:
            return None

    def is_night(
        self,
        *,
        now: datetime | None = None,
        timezone_name: str | None = None,
        settings: Any | None = None,
    ) -> bool:
        """Verifica se ``now`` está dentro da janela noturna (ex.: 22:00–05:00).

        A janela **atravessa a meia-noite**: se ``start_hour > end_hour``, a noite
        começa em ``start`` do dia corrente e termina em ``end`` do dia seguinte.
        """
        cfg = settings or get_settings()
        if not cfg.nfc_monitor_enabled:
            return False
        moment = now or datetime.now(self._zone(timezone_name)).astimezone(
            self._zone(timezone_name) or timezone.utc
        )
        hour = moment.hour
        start = cfg.nfc_night_start_hour
        end = cfg.nfc_night_end_hour
        if start == end:
            return False
        if start < end:
            return start <= hour < end
        # Janela que atravessa a meia-noite: das 22:00 às 05:00.
        return hour >= start or hour < end

    def night_date(
        self,
        *,
        now: datetime | None = None,
        timezone_name: str | None = None,
    ) -> str:
        """Data local da noite em vigor (YYYY-MM-DD).

        Para a janela 22:00–05:00, uma detecção às 01:30 do dia 21 pertence à
        noite que começou no dia 20 às 22:00.
        """
        zone = self._zone(timezone_name)
        moment = now or datetime.now(zone or timezone.utc)
        moment = moment.astimezone(zone or timezone.utc)
        if self.is_night(now=moment, timezone_name=timezone_name):
            start = get_settings().nfc_night_start_hour
            if moment.hour < start:
                return (moment - timedelta(days=1)).date().isoformat()
        return moment.date().isoformat()

    def effective_confidence_threshold(
        self,
        base: float,
        *,
        now: datetime | None = None,
        timezone_name: str | None = None,
        settings: Any | None = None,
    ) -> float:
        """Limiar efetivo: reduzido dentro da janela noturna."""
        cfg = settings or get_settings()
        if not cfg.nfc_monitor_enabled:
            return base
        if self.is_night(now=now, timezone_name=timezone_name, settings=cfg):
            return min(base, max(0.20, cfg.nfc_confidence_threshold))
        return base

    def classify_nfc_score(
        self,
        *,
        common_name: str,
        scientific_name: str,
        confidence: float,
        is_night: bool,
    ) -> float:
        """Pontuação 0..1 de "voo migratório" para a galeria noturna.

        Combina fatores: horário noturno, confiança dentro da faixa típica de
        chamados fracos e o nome da espécie. Quanto maior, mais provável de ser
        um *flight call* real.
        """
        if not is_night:
            return 0.0
        score = 0.5
        # Chamados fracos (0.45–0.75) são típicos de NFC; muito baixo = ruído,
        # muito alto = ave próxima no comedouro (não voo).
        if 0.35 <= confidence <= 0.80:
            score += 0.25
        # Espécies conhecidas como migrantes noturnos ganham bônus.
        tokens = {
            "sabiá",
            "tapaculo",
            "bem-te-vi",
        }
        casefolded = f"{common_name} {scientific_name}".casefold()
        if any(token in casefolded for token in tokens):
            score += 0.15
        return round(min(1.0, score), 2)

    def maybe_report_transition(
        self,
        *,
        is_night: bool,
        on_transition: Any | None = None,
    ) -> None:
        """Registra a transição dia ↔ noite uma única vez por mudança."""
        if self._last_nfc_active is None:
            self._last_night = is_night
            self._last_nfc_active = is_night
            return
        if is_night == self._last_nfc_active:
            return
        self._last_nfc_active = is_night
        try:
            if on_transition is not None:
                on_transition(is_night)
            logger.info(
                "Escuta noturna de migração %s.",
                "ativada" if is_night else "desativada",
            )
        except Exception:
            logger.debug("Falha ao reportar transição NFC", exc_info=True)


def get_nfc_monitor() -> NfcMonitor:
    """Instância singleton do monitor NFC."""
    return NfcMonitor()


# Compatibilidade com importações existentes.
NfcMonitorService = NfcMonitor
