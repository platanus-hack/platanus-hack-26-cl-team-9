"""Digital engine: what supervision shows, given the real state (docs/strategy.md sections 2-3).

Per area, supervision may be missing (telemetry or comms lost, segmented), stale (delayed), or
unreliable (values that look normal but are frozen and biased). Alarms come from physical changes
seen through supervision, from defence and control self-checks, and from noise (false alarms).
`uncertainty` 0 is perfect information, 1 the baseline, 2 a degraded environment.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from cascadasen.domain.cascade.frequency import F0
from cascadasen.domain.theater.areas import TheaterNetwork
from cascadasen.domain.theater.state import Alarm, AreaObs, ObservedState, RealState

FALSE_ALARM_KINDS = ("load_loss", "breaker_open", "data_anomaly", "defense_fault", "control_lost")


@dataclass(frozen=True)
class Truth:
    """Evaluator-only metadata about an observation (never given to agents)."""

    false_alarms: tuple[Alarm, ...]
    observable: tuple[str, ...]


def _poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def corridor_status(real: RealState, cid: str) -> str:
    return "closed" if real.grid.corridor_closed(cid) else "open"


@dataclass
class _Observer:
    """One observation pass. Methods run in a fixed order so the seeded noise is reproducible."""

    network: TheaterNetwork
    real: RealState
    history: list[dict[str, tuple[float, bool]]]
    prev: ObservedState | None
    rng: random.Random
    uncertainty: float
    cfg: dict[str, float]
    defense_areas: dict[str, list[str]]
    alarms: list[Alarm] = field(default_factory=list)
    false_alarms: list[Alarm] = field(default_factory=list)
    observable: list[str] = field(default_factory=list)

    @property
    def oracle(self) -> bool:
        return self.uncertainty <= 0

    def maybe(self, p: float) -> bool:
        return self.oracle or self.rng.random() < p

    def area(self, a: str) -> AreaObs:
        d, cfg = self.real.digital[a], self.cfg
        load, floor = self.real.grid.load_mw[a], cfg["telemetry_floor"]
        if self.oracle:  # perfect information: exact current values and the true state of supervision
            served, energized = self.history[-1][a]
            self.observable.append(a)
            if d.comms == "down" and not d.manual_ops:
                self.alarms.append(Alarm(a, "comms_lost"))
            elif not d.observable(floor):
                self.alarms.append(Alarm(a, "telemetry_lost"))
            g = self.real.grid
            return AreaObs(
                a,
                served,
                load,
                energized,
                d.delay,
                d.comms,
                d.telemetry,
                d.manual_ops,
                d.segmented,
                g.freq_hz.get(a),
                g.rocof_hz_s.get(a, 0.0),
            )
        if not d.observable(floor):
            self.alarms.append(Alarm(a, "comms_lost" if d.comms == "down" else "telemetry_lost"))
            return AreaObs(a, None, load, None, 0, d.comms, 0.0, d.manual_ops, d.segmented)
        self.observable.append(a)
        lag = d.delay + (int(cfg["backup_comms_delay"]) if d.comms == "backup" or d.manual_ops else 0)
        past = self.history[max(0, len(self.history) - 1 - lag)]
        served, energized = past[a]
        if not d.reliable:  # frozen and biased values that look normal
            base = d.frozen_served if d.frozen_served is not None else past[a][0]
            served, energized = base * (1 + d.bias), True
        share = 1.0 if d.manual_ops else max(d.telemetry, floor)
        noise = self.rng.gauss(0.0, cfg["base_noise"] * self.uncertainty / share) if served > 0 else 0.0
        freq, rocof = self.frequency(a, lag, d.reliable, energized, share)
        return AreaObs(
            a,
            max(0.0, served * (1 + noise)),
            load,
            energized,
            lag,
            d.comms,
            share,
            d.manual_ops,
            d.segmented,
            freq,
            rocof,
        )

    def frequency(
        self, a: str, lag: int, reliable: bool, energized: bool | None, share: float
    ) -> tuple[float | None, float | None]:
        """Frequency and RoCoF as supervision shows them. Stale data shows the steady state before the
        event (f0); unreliable data looks normal (f0, the hardest case); fresh data carries noise."""
        if energized is False:
            return None, None
        if lag > 0 or not reliable:
            return F0, 0.0
        g = self.real.grid
        f, r = g.freq_hz.get(a), g.rocof_hz_s.get(a, 0.0)
        if f is None:
            return None, None
        sd = self.cfg.get("freq_noise_hz", 0.0) * self.uncertainty / share
        return f + (self.rng.gauss(0.0, sd) if sd > 0 else 0.0), r

    def physical_alarms(self, areas: list[AreaObs]) -> list[tuple[str, str | None]]:
        by_area = {o.area: o for o in areas}
        if self.prev is not None:
            for o in areas:
                p = self.prev.area(o.area)
                if o.served_mw is not None and p.served_mw is not None and o.served_mw < 0.95 * p.served_mw:
                    self.alarms.append(Alarm(o.area, "load_loss"))
                if o.energized is False and p.energized is not False:
                    self.alarms.append(Alarm(o.area, "blackout"))
        corridors = []
        for cid, c in self.network.corridors.items():
            seen = [x for x in (c.a, c.b) if by_area[x].served_mw is not None]
            trusted = self.oracle or any(self.real.digital[x].reliable for x in seen)
            status = corridor_status(self.real, cid) if seen and trusted else None
            corridors.append((cid, status))
            if status == "open" and self.prev is not None and self.prev.corridor(cid) == "closed":
                self.alarms.append(Alarm(seen[0], "breaker_open"))
        lt = self.real.last_transient
        if lt and lt.get("cycle") == self.real.cycle:
            for isl in lt.get("islands", []):
                where = next((x for x in isl["nodes"] if by_area[x].served_mw is not None), isl["nodes"][0])
                if isl["load_shed_mw"] > 0 or isl["result"] in ("blackout", "uncertain"):
                    self.alarms.append(Alarm(where, "frequency_event"))
                if isl["result"] == "uncertain" and by_area[where].served_mw is not None:
                    self.alarms.append(Alarm(where, "voltage_limited"))
        self.band_alarms(areas)
        return corridors

    def band_alarms(self, areas: list[AreaObs]) -> None:
        """docs/agents.md 1.2: observed frequency outside the operating band, a steep initial RoCoF, and an
        island whose inertia fell below the floor after losing synchronous units (one alarm per island)."""
        cfg, g = self.cfg, self.real.grid
        lo, hi = cfg.get("band_low_hz", 49.0), cfg.get("band_high_hz", 51.0)
        for o in areas:
            if o.freq_hz is not None and not lo <= o.freq_hz <= hi:
                self.alarms.append(Alarm(o.area, "frequency_out_of_band"))
            if o.rocof_hz_s is not None and abs(o.rocof_hz_s) >= cfg.get("high_rocof_hz_s", 1.0):
                self.alarms.append(Alarm(o.area, "high_rocof"))
        floor = cfg.get("low_inertia_mws", 0.0)
        if floor <= 0:
            return
        seen = {o.area for o in areas if o.served_mw is not None and self.real.digital[o.area].reliable}
        for isl in g.islands():
            here = [
                a for a in self.network.order if a in seen and set(self.network.areas[a].buses) & set(isl)
            ]
            if not here:
                continue
            now, plan = float(g.inertia[isl].sum()), float(g.plan_inertia[isl].sum())
            if now < floor and now < 0.9 * plan:
                self.alarms.append(Alarm(here[0], "low_inertia"))

    def self_checks(self) -> None:
        """Defence and control self-checks, dependency notices and integrity detection."""
        cfg, real = self.cfg, self.real
        for did in sorted(real.grid.disabled_defenses):
            for a in self.defense_areas.get(did, []):
                if (
                    a in self.observable
                    and real.digital[a].reliable
                    and self.maybe(cfg["defense_fault_detect_p"])
                ):
                    self.alarms.append(Alarm(a, "defense_fault"))
                    break
        for a in self.network.order:
            d = real.digital[a]
            if not d.remote_control and d.comms != "down" and self.maybe(cfg["control_lost_detect_p"]):
                self.alarms.append(Alarm(a, "control_lost"))
            if not d.external_ok and self.maybe(cfg["external_notice_p"]):
                self.alarms.append(Alarm(a, "external_service"))
            if not d.reliable and a in self.observable:
                tasked = d.tasked_until >= real.cycle
                if self.maybe(cfg["unreliable_detect_p_tasked"] if tasked else cfg["unreliable_detect_p"]):
                    self.alarms.append(Alarm(a, "data_anomaly"))
            if not self.oracle:
                self.noise_alarms(a, d.false_alarm_rate)

    def noise_alarms(self, a: str, injected_rate: float) -> None:
        lam = self.cfg["base_false_alarm_rate"] * self.uncertainty + injected_rate
        for _ in range(_poisson(self.rng, lam)):
            fa = Alarm(a, self.rng.choice(FALSE_ALARM_KINDS))
            self.alarms.append(fa)
            self.false_alarms.append(fa)


def observe(
    network: TheaterNetwork,
    real: RealState,
    history: list[dict[str, tuple[float, bool]]],
    prev: ObservedState | None,
    rng: random.Random,
    uncertainty: float,
    cfg: dict[str, float],
    defense_areas: dict[str, list[str]],
) -> tuple[ObservedState, Truth]:
    o = _Observer(network, real, history, prev, rng, max(uncertainty, 0.0), cfg, defense_areas)
    areas = [o.area(a) for a in network.order]
    corridors = o.physical_alarms(areas)
    o.self_checks()
    order = {a: i for i, a in enumerate(network.order)}
    alarms = sorted(o.alarms, key=lambda x: (order.get(x.area, 99), x.kind))
    return (
        ObservedState(real.cycle, tuple(areas), tuple(corridors), tuple(alarms)),
        Truth(tuple(o.false_alarms), tuple(o.observable)),
    )
