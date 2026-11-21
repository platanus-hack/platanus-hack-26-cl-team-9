"""Digital engine: what supervision shows, given the real state (docs/strategy.md sections 2-3).

Per area, supervision may be missing (telemetry or comms lost, segmented), stale (delayed), or
unreliable (values that look normal but are frozen and biased). Alarms come from physical changes
seen through supervision, from defence and control self-checks, and from noise (false alarms).
`uncertainty` 0 is perfect information, 1 the baseline, 2 a degraded environment.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from cascadasen.domain.simulation.network import ReducedNetwork
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


def corridor_status(network: ReducedNetwork, real: RealState, cid: str) -> str:
    return "closed" if real.grid.corridor(network, cid) is not None else "open"


def observe(
    network: ReducedNetwork,
    real: RealState,
    history: list[dict[str, tuple[float, bool]]],
    prev: ObservedState | None,
    rng: random.Random,
    uncertainty: float,
    cfg: dict[str, float],
    defense_areas: dict[str, list[str]],
) -> tuple[ObservedState, Truth]:
    oracle = uncertainty <= 0
    factor = max(uncertainty, 0.0)
    floor = cfg["telemetry_floor"]
    areas: list[AreaObs] = []
    alarms: list[Alarm] = []
    false_alarms: list[Alarm] = []
    observable: list[str] = []
    now = history[-1]
    for a in network.order:
        d = real.digital[a]
        load = real.grid.load_mw[a]
        if oracle:
            served, energized = now[a]
            areas.append(AreaObs(a, served, load, energized, 0, d.comms, 1.0, d.manual_ops, d.segmented))
            observable.append(a)
            continue
        if not d.observable(floor):
            areas.append(AreaObs(a, None, load, None, 0, d.comms, 0.0, d.manual_ops, d.segmented))
            if d.comms == "down":
                alarms.append(Alarm(a, "comms_lost"))
            else:
                alarms.append(Alarm(a, "telemetry_lost"))
            continue
        observable.append(a)
        lag = d.delay + (int(cfg["backup_comms_delay"]) if d.comms == "backup" or d.manual_ops else 0)
        past = history[max(0, len(history) - 1 - lag)]
        if d.reliable:
            served, energized = past[a]
        else:
            served, energized = (
                (d.frozen_served if d.frozen_served is not None else past[a][0]) * (1 + d.bias),
                True,
            )
        share = 1.0 if d.manual_ops else max(d.telemetry, floor)
        noise = rng.gauss(0.0, cfg["base_noise"] * factor / share) if served > 0 else 0.0
        areas.append(
            AreaObs(
                a,
                max(0.0, served * (1 + noise)),
                load,
                energized,
                lag,
                d.comms,
                share,
                d.manual_ops,
                d.segmented,
            )
        )
    obs_by_area = {o.area: o for o in areas}

    # physical changes seen through supervision
    if prev is not None:
        for o in areas:
            p = prev.area(o.area)
            if o.served_mw is not None and p.served_mw is not None and o.served_mw < 0.95 * p.served_mw:
                alarms.append(Alarm(o.area, "load_loss"))
            if o.energized is False and p.energized is not False:
                alarms.append(Alarm(o.area, "blackout"))
    corridors = []
    for cid, c in network.corridors.items():
        seen = [obs_by_area[x] for x in (c.a, c.b) if obs_by_area[x].served_mw is not None]
        reliable = oracle or any(
            real.digital[x].reliable for x in (c.a, c.b) if obs_by_area[x].served_mw is not None
        )
        status = corridor_status(network, real, cid) if seen and reliable else None
        corridors.append((cid, status))
        if status == "open" and prev is not None and prev.corridor(cid) == "closed":
            alarms.append(Alarm(seen[0].area, "breaker_open"))

    lt = real.last_transient
    if lt and lt.get("cycle") == real.cycle:
        for isl in lt.get("islands", []):
            if isl["load_shed_mw"] > 0 or isl["result"] in ("blackout", "uncertain"):
                where = next((x for x in isl["nodes"] if obs_by_area[x].served_mw is not None), None)
                alarms.append(Alarm(where or isl["nodes"][0], "frequency_event"))

    def maybe(p: float) -> bool:
        return oracle or rng.random() < p

    for did in sorted(real.grid.disabled_defenses):
        for a in defense_areas.get(did, []):
            if a in observable and real.digital[a].reliable and maybe(cfg["defense_fault_detect_p"]):
                alarms.append(Alarm(a, "defense_fault"))
                break
    for a in network.order:
        d = real.digital[a]
        if not d.remote_control and d.comms != "down" and maybe(cfg["control_lost_detect_p"]):
            alarms.append(Alarm(a, "control_lost"))
        if not d.external_ok and maybe(cfg["external_notice_p"]):
            alarms.append(Alarm(a, "external_service"))
        if not d.reliable and a in observable:
            p = (
                cfg["unreliable_detect_p_tasked"]
                if d.tasked_until >= real.cycle
                else cfg["unreliable_detect_p"]
            )
            if maybe(p):
                alarms.append(Alarm(a, "data_anomaly"))
        if not oracle:
            lam = cfg["base_false_alarm_rate"] * factor + d.false_alarm_rate
            for _ in range(_poisson(rng, lam)):
                fa = Alarm(a, rng.choice(FALSE_ALARM_KINDS))
                alarms.append(fa)
                false_alarms.append(fa)

    order = {a: i for i, a in enumerate(network.order)}
    alarms.sort(key=lambda x: (order.get(x.area, 99), x.kind))
    return (
        ObservedState(real.cycle, tuple(areas), tuple(corridors), tuple(alarms)),
        Truth(tuple(false_alarms), tuple(observable)),
    )
