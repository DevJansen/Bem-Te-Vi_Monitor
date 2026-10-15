"""Polygonal zone validator with dwell, cooldown and absence tolerance."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from app.domain.models import Point, ZoneConfig

logger = logging.getLogger(__name__)

# Tolerância mínima (em segundos) de ausência antes de encerrar uma presença.
# Garante que perdas momentâneas de detecção (ave imóvel ou oclusão breve) não
# reiniciem o contador de permanência (dwell) a cada quadro. Complementa a
# retenção de rastreio do BoxTracker.
MIN_ABSENCE_GRACE_SECONDS = 10.0


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
    """
    Tracks bird presence inside polygonal zones.

    - min_dwell_seconds: bird must remain (with tolerance) before trigger
    - absence_tolerance_seconds: brief exits do not reset the dwell timer
    - cooldown_seconds: suppress re-triggers after a successful event
    """

    zones: list[ZoneConfig] = field(default_factory=list)
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
                cooled = (
                    state.last_triggered_at is None
                    or (now - state.last_triggered_at) >= state.zone.cooldown_seconds
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
                    if absent > max(
                        state.zone.absence_tolerance_seconds,
                        MIN_ABSENCE_GRACE_SECONDS,
                    ):
                        state.inside_since = None
                        state.last_seen_inside = None
                        state.triggered_for_presence = False
                else:
                    state.inside_since = None
                    state.triggered_for_presence = False

        return triggers
