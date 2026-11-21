"""Field crews on the map (docs/strategy.md sections 4 and 6).

Each crew has a home base (an operating area) and a current position. Sending it somewhere takes
a mobilisation time plus road travel between area centroids, with spread from the `field` stream.
A crew that finishes a task stays where it is; the next task leaves from there. The `Ledger` still
counts `field_crews` for the validator; the roster decides which crew goes and when it arrives.

A timed task frees its crew at its end cycle; a held task (manual operation, a repair) frees it
when the ledger no longer holds it (`sync`). A crew is never sent if it would arrive after
`max_eta` cycles: in an incident of a few hours, a crew hours away is no help.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

from cascadasen.domain.simulation.network import ReducedNetwork

EARTH_KM = 6371.0


@dataclass
class Crew:
    id: str
    base: str
    position: str
    task: str | None = None  # action key it is working on
    target: str | None = None
    arrival: int | None = None
    until: int | None = None  # cycle the task ends; None = until the ledger releases it

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "base": self.base,
            "position": self.position,
            "task": self.task,
            "target": self.target,
            "arrival": self.arrival,
            "status": "free" if self.task is None else "busy",
        }


@dataclass(frozen=True)
class Assignment:
    crew: str
    site: str
    arrival: int


def _km(network: ReducedNetwork, a: str, b: str) -> float | None:
    A, B = network.areas[a], network.areas[b]
    if None in (A.lat, A.lon, B.lat, B.lon):
        return None
    la1, lo1, la2, lo2 = map(math.radians, (A.lat, A.lon, B.lat, B.lon))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


def travel_table(
    network: ReducedNetwork, params: dict[str, Any], cycle_minutes: float
) -> dict[tuple[str, str], float]:
    """Median travel time in cycles between every pair of areas (mobilisation included)."""
    order = network.order
    km = {(a, b): _km(network, a, b) for a in order for b in order}
    known = sorted(v for v in km.values() if v)
    median_km = known[len(known) // 2] if known else 0.0
    per_cycle_km = float(params["road_speed_kmh"]) * cycle_minutes / 60.0
    mob = float(params["mobilisation_cycles"])
    return {
        pair: mob + (d if d is not None else median_km) * float(params["road_factor"]) / per_cycle_km
        for pair, d in km.items()
    }


@dataclass
class CrewRoster:
    crews: list[Crew]
    travel: dict[tuple[str, str], float]
    sigma: float = 0.0
    rng: random.Random | None = None
    max_eta: int | None = None
    log: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def build(
        cls,
        network: ReducedNetwork,
        count: int,
        params: dict[str, Any],
        cycle_minutes: float,
        rng: random.Random | None = None,
    ) -> CrewRoster:
        bases = [b for b in params["bases"] if b in network.areas] or list(network.order)
        crews = [Crew(f"K{i + 1}", bases[i % len(bases)], bases[i % len(bases)]) for i in range(int(count))]
        max_eta = params.get("max_eta_cycles")
        return cls(
            crews,
            travel_table(network, params, cycle_minutes),
            float(params["travel_sigma"]),
            rng,
            int(max_eta) if max_eta is not None else None,
        )

    def eta(self, crew: Crew, site: str) -> float:
        return self.travel[(crew.position, site)]

    def best_eta(self, site: str) -> int | None:
        """Median cycles until the nearest free crew could be on site (what Logistics sees)."""
        free = [self.eta(c, site) for c in self.crews if c.task is None]
        return math.ceil(min(free)) if free else None

    def dispatch(self, sites: list[str], task: str, now: int, work: int | None = None) -> Assignment | None:
        """Send the free crew that reaches one of `sites` first; `work` cycles on site (None: held).
        Returns None when no free crew can arrive within `max_eta`. Travel spread is drawn here."""
        options = [(self.eta(c, s), c.id, c, s) for c in self.crews if c.task is None for s in sites]
        options = [o for o in options if self.max_eta is None or o[0] <= self.max_eta]
        if not options:
            return None
        median, _, crew, site = min(options)
        travel = median * math.exp(self.rng.gauss(0.0, self.sigma)) if self.rng and self.sigma else median
        arrival = now + max(1, math.ceil(travel))
        crew.task, crew.target, crew.arrival = task, site, arrival
        crew.until = arrival + work if work is not None else None
        self.log.append(
            {"cycle": now, "crew": crew.id, "from": crew.position, "to": site, "arrival": arrival}
        )
        return Assignment(crew.id, site, arrival)

    def sync(self, now: int, held: set[str]) -> list[str]:
        """Free crews whose task ended or is no longer held; they stay at their target."""
        freed = []
        for c in self.crews:
            if c.task is None:
                continue
            done = now >= c.until if c.until is not None else c.task not in held
            if done:
                if c.arrival is not None and now >= c.arrival:
                    c.position = c.target or c.position
                c.task = c.target = c.arrival = c.until = None
                freed.append(c.id)
        return freed

    def snapshot(self) -> list[dict[str, Any]]:
        return [c.as_dict() for c in self.crews]
