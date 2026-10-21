"""Polygonal zone validator with dwell, cooldown and absence tolerance."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from app.domain.models import Point, ZoneConfig

logger = logging.getLogger(__name__)

# Tolerância MÍNIMA absoluta (em segundos) de ausência antes de encerrar uma
# presença. É apenas um piso de segurança: o valor efetivo vem de
# ``presence_grace_seconds`` (config) combinado com o ``absence_tolerance_seconds``
# da zona. Complementa a retenção de rastreio do BoxTracker.
MIN_ABSENCE_GRACE_SECONDS = 1.0


def point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    """Ray-casting point-in-polygon for normalized coordinates."""
    if len(polygon) < 3:
        return False
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        intersect = ((yi > y) != (yj > y)) and (
            x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


FULL_FRAME_ZONE = ZoneConfig(
    id="full_frame",
    name="full_frame",
    points=[
        Point(x=0.0, y=0.0),
        Point(x=1.0, y=0.0),
        Point(x=1.0, y=1.0),
        Point(x=0.0, y=1.0),
    ],
    min_dwell_seconds=1.5,
    cooldown_seconds=30.0,
    absence_tolerance_seconds=1.0,
    enabled=True,
)


@dataclass
class ZoneRuntimeState:
    zone: ZoneConfig
    inside_since: float | None = None
    last_seen_inside: float | None = None
    last_triggered_at: float | None = None
    triggered_for_presence: bool = False

    @property
    def polygon(self) -> list[tuple[float, float]]:
        return [(p.x, p.y) for p in self.zone.points]


@dataclass
class ZoneTrigger:
    zone_id: str
    zone_name: str
    dwell_seconds: float
    point: tuple[float, float]


@dataclass
class ZoneValidator:
    """Rastreia a presença de aves nas zonas poligonais (dwell + supressão).

    - ``min_dwell_seconds``: a ave precisa permanecer (com tolerância) antes de
      disparar.
    - ``absence_tolerance_seconds``: saídas breves não reiniciam o dwell.
    - ``cooldown_seconds``: suprime novos disparos logo após um evento.
    - ``presence_grace_seconds``: ausência necessária para ENCERRAR a presença
      (piso global). Enquanto a ave permanecer, nenhum novo alerta é emitido —
      é a regra anti-spam "mesma ave = mesmo evento".
    - ``alert_cooldown_seconds``: piso global do cooldown por zona.
    """

    zones: list[ZoneConfig] = field(default_factory=list)
    # Piso global: tempo de ausência para encerrar a presença (anti-spam).
    presence_grace_seconds: float = 30.0
    # Piso global: intervalo mínimo entre alertas na mesma zona.
    alert_cooldown_seconds: float = 30.0
    _states: dict[str, ZoneRuntimeState] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self.set_zones(self.zones)

    def set_zones(self, zones: list[ZoneConfig]) -> None:
        enabled = [z for z in zones if z.enabled]
        if not enabled:
            enabled = [FULL_FRAME_ZONE]
        previous_states = self._states
        self.zones = enabled
        self._states = {}
        for zone in self.zones:
            previous = previous_states.get(zone.id)
            if previous is not None and previous.zone == zone:
                previous.zone = zone
                self._states[zone.id] = previous
            else:
                self._states[zone.id] = ZoneRuntimeState(zone=zone)

    def update(
        self,
        normalized_points: list[tuple[float, float]],
        now: float | None = None,
    ) -> list[ZoneTrigger]:
        """
        Feed current detection centers (normalized 0..1).
        Returns zone triggers that just became valid.
        """
        now = time.time() if now is None else now
        triggers: list[ZoneTrigger] = []

        for zone_id, state in self._states.items():
            inside_points = [
                p
                for p in normalized_points
                if point_in_polygon(p[0], p[1], state.polygon)
            ]
            is_inside = len(inside_points) > 0

            if is_inside:
                state.last_seen_inside = now
                if state.inside_since is None:
                    state.inside_since = now
                    state.triggered_for_presence = False

                dwell = now - state.inside_since
                # Cooldown efetivo: piso global + valor da zona.
                cooldown = max(
                    state.zone.cooldown_seconds, self.alert_cooldown_seconds
                )
                cooled = (
                    state.last_triggered_at is None
                    or (now - state.last_triggered_at) >= cooldown
                )
                if (
                    not state.triggered_for_presence
                    and cooled
                    and dwell >= state.zone.min_dwell_seconds
                ):
                    state.triggered_for_presence = True
                    state.last_triggered_at = now
                    triggers.append(
                        ZoneTrigger(
                            zone_id=zone_id,
                            zone_name=state.zone.name,
                            dwell_seconds=dwell,
                            point=inside_points[0],
                        )
                    )
            else:
                if state.last_seen_inside is not None:
                    absent = now - state.last_seen_inside
                    # A presença só termina após a tolerância da zona E o piso
                    # global (presence_grace_seconds). Isso evita re-alertas da
                    # mesma ave quando o YOLO a perde por alguns instantes.
                    grace = max(
                        state.zone.absence_tolerance_seconds,
                        self.presence_grace_seconds,
                        MIN_ABSENCE_GRACE_SECONDS,
                    )
                    if absent > grace:
                        state.inside_since = None
                        state.last_seen_inside = None
                        state.triggered_for_presence = False
                else:
                    state.inside_since = None
                    state.triggered_for_presence = False

        return triggers

    def has_active_presence(self) -> bool:
        """Indica se alguma zona tem presença ativa (mesmo sem novo disparo)."""
        return any(state.inside_since is not None for state in self._states.values())

    def active_presence_zones(self) -> list[str]:
        """Nomes das zonas com presença ativa agora (para o log do Bem-Te-Vi Core)."""
        return [
            state.zone.name
            for state in self._states.values()
            if state.inside_since is not None
        ]
