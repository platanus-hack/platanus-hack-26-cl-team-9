"""Real and observed state (docs/strategy.md section 3).

`RealState` is what is happening: the physical grid (`GridState`), the true health of supervision
per area, and the abstract effects in force. Only the engine, the validator and the evaluator read
it. `ObservedState` is what supervision shows; it is immutable and it is what agents receive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cascadasen.domain.simulation.grid import GridState


@dataclass
class AreaDigital:
    """True health of supervision and control in one operating area."""

    telemetry: float = 1.0  # share of telemetry points reporting
    delay: int = 0  # cycles of staleness
    reliable: bool = True  # False: values look normal but are wrong
    bias: float = 0.0
    frozen_served: float | None = None  # what unreliable data keeps showing
    comms: str = "primary"  # primary | backup | down (derived from the two flags below)
    primary_ok: bool = True
    backup_active: bool = False
    remote_control: bool = True
    false_alarm_rate: float = 0.0
    segmented: bool = False
    manual_ops: bool = False
    tasked_until: int = -1  # ISR monitoring boost
    external_ok: bool = True

    def observable(self, floor: float) -> bool:
        if self.segmented and not self.manual_ops:
            return False
        if self.comms == "down" and not self.manual_ops:
            return False
        return self.telemetry >= floor or self.manual_ops

    def health(self) -> float:
        """0-1 supervision quality used for the observability indicator."""
        if self.segmented and not self.manual_ops:
            return 0.0
        if self.comms == "down" and not self.manual_ops:
            return 0.0
        q = min(1.0, self.telemetry) if not self.manual_ops else 0.6
        if self.comms == "backup":
            q *= 0.8
        if not self.reliable:
            q *= 0.3
        if self.delay:
            q *= 0.7
        return round(q, 3)


@dataclass
class Effect:
    """An abstract event in force in the real world."""

    id: str
    event: str
    target: str
    area: str | None
    params: dict[str, Any]
    source: str  # scenario | user | adversary
    cause: str  # intentional | failure
    start: int
    expires: int | None = None
    cleared: int | None = None
    established: bool = True

    def active(self, cycle: int) -> bool:
        if not self.established or self.cleared is not None:
            return False
        return self.expires is None or cycle < self.expires


@dataclass
class RealState:
    cycle: int
    grid: GridState
    digital: dict[str, AreaDigital]
    effects: list[Effect] = field(default_factory=list)
    last_transient: dict[str, Any] | None = None
    worst_level: str = "L0"

    def active_effects(self, area: str | None = None) -> list[Effect]:
        return [e for e in self.effects if e.active(self.cycle) and (area is None or e.area == area)]


@dataclass(frozen=True)
class AreaObs:
    area: str
    served_mw: float | None
    load_mw: float  # demand forecast: always known to operators
    energized: bool | None
    age: int
    comms: str
    telemetry: float
    manual_ops: bool
    segmented: bool


@dataclass(frozen=True)
class Alarm:
    area: str
    kind: str


@dataclass(frozen=True)
class ObservedState:
    cycle: int
    areas: tuple[AreaObs, ...]
    corridors: tuple[tuple[str, str | None], ...]
    alarms: tuple[Alarm, ...]

    def area(self, area_id: str) -> AreaObs:
        return next(a for a in self.areas if a.area == area_id)

    def corridor(self, cid: str) -> str | None:
        return dict(self.corridors).get(cid)

    def alarms_in(self, area_id: str) -> list[Alarm]:
        return [a for a in self.alarms if a.area == area_id]

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle": self.cycle,
            "areas": {
                a.area: {
                    "served_mw": None if a.served_mw is None else round(a.served_mw, 1),
                    "load_mw": round(a.load_mw, 1),
                    "energized": a.energized,
                    "age": a.age,
                    "comms": a.comms,
                    "telemetry": round(a.telemetry, 2),
                    "manual_ops": a.manual_ops,
                    "segmented": a.segmented,
                }
                for a in self.areas
            },
            "corridors": dict(self.corridors),
            "alarms": [{"area": a.area, "kind": a.kind} for a in self.alarms],
        }
