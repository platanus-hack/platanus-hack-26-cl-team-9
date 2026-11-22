"""Physical state of the reduced network and the operating points that seed it.

`GridState` is the real physical state the engine evolves: demand and served load per area,
online and tripped generation by technology, inertia, reserve, open elements and defences.
`build_state` turns an operating point (`params/operating_points.yaml`) into a balanced state.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

from cascadasen.domain.simulation.network import ReducedNetwork
from cascadasen.domain.simulation.params import Provenance, collect_provenance, load_params, value

MIN_SYNC_SHARE = 0.35  # floor of synchronous dispatch as a share of load, keeps islands with inertia


class UnknownOperatingPointError(KeyError):
    pass


@dataclass(frozen=True)
class Physics:
    """Engine constants from `params/physics.yaml`."""

    f0: float
    dt: float
    horizon: float
    frame_step: float
    blackout_hz: float
    overfrequency_hz: float
    damping_pct_per_hz: float
    reserve_share: float
    reserve_tau: float
    reserve_full_dev: float
    inertia_h: dict[str, float]
    overload_ratio: float
    weak_link_window: float
    max_iterations: int
    battery_delay: float
    battery_ramp: float
    local_cut_mw: float
    voll_usd_per_kwh: float
    default_outage_h: float
    provenance: tuple[Provenance, ...] = ()

    @classmethod
    def load(cls) -> Physics:
        p = load_params("physics")
        v = {k: value(p[k], k) for k in p if k != "version"}
        return cls(
            f0=v["f0_hz"],
            dt=v["dt_s"],
            horizon=v["horizon_s"],
            frame_step=v["frame_step_s"],
            blackout_hz=v["blackout_hz"],
            overfrequency_hz=v["overfrequency_trip_hz"],
            damping_pct_per_hz=v["load_damping_pct_per_hz"],
            reserve_share=v["reserve_share_of_sync"],
            reserve_tau=v["reserve_time_constant_s"],
            reserve_full_dev=v["reserve_full_deviation_hz"],
            inertia_h=dict(v["inertia_h_s"]),
            overload_ratio=v["overload_trip_ratio"],
            weak_link_window=v["weak_link_window_s"],
            max_iterations=int(v["max_cascade_iterations"]),
            battery_delay=v["battery_delay_s"],
            battery_ramp=v["battery_ramp_s"],
            local_cut_mw=v["local_cut_mw"],
            voll_usd_per_kwh=v["voll_usd_per_kwh"],
            default_outage_h=v["default_outage_h"],
            provenance=tuple(collect_provenance(p, "physics")),
        )

    @property
    def sync_techs(self) -> frozenset[str]:
        return frozenset(self.inertia_h)


@dataclass
class GridState:
    operating_point: str
    load_mw: dict[str, float]
    served_mw: dict[str, float]
    gen_mw: dict[str, dict[str, float]]
    tripped_mw: dict[str, dict[str, float]]
    kinetic_mws: dict[str, float]
    h_phys: dict[str, float]
    reserve_share: dict[str, float]
    sync_techs: frozenset[str]
    reserve_extra_mw: dict[str, float] = field(default_factory=dict)
    battery_mw: dict[str, float] = field(default_factory=dict)
    out_lines: set[str] = field(default_factory=set)
    open_corridors: set[str] = field(default_factory=set)
    out_nodes: set[str] = field(default_factory=set)
    blackout_areas: set[str] = field(default_factory=set)
    disabled_defenses: set[str] = field(default_factory=set)
    no_reserve_areas: set[str] = field(default_factory=set)
    reserve_used_mw: dict[str, float] = field(default_factory=dict)
    provenance: tuple[Provenance, ...] = ()

    def copy(self) -> GridState:
        return copy.deepcopy(self)

    # ------------------------------------------------------------ aggregates

    def gen(self, area: str) -> float:
        return sum(self.gen_mw.get(area, {}).values())

    def sync_gen(self, area: str) -> float:
        return sum(mw for t, mw in self.gen_mw.get(area, {}).items() if t in self.sync_techs)

    def inertia_mws(self, area: str) -> float:
        """Kinetic energy of online synchronous units in MW·s (GVAs × 1000). Tracked as state:
        tripping a unit removes its own inertia (H × MW), not the area average (stack.md 4.4)."""
        if area in self.blackout_areas or self.sync_gen(area) <= 0:
            return 0.0
        return max(0.0, self.kinetic_mws.get(area, 0.0))

    def remove_inertia(self, area: str, tech: str, mw: float) -> None:
        if tech in self.sync_techs:
            self.kinetic_mws[area] = max(
                0.0, self.kinetic_mws.get(area, 0.0) - self.h_phys.get(tech, 0.0) * mw
            )

    def reserve_mw(self, area: str) -> float:
        if area in self.no_reserve_areas or area in self.blackout_areas:
            return 0.0
        base = self.reserve_share.get(area, 0.0) * self.sync_gen(area)
        return max(0.0, base - self.reserve_used_mw.get(area, 0.0)) + self.reserve_extra_mw.get(area, 0.0)

    def corridor(self, network: ReducedNetwork, cid: str) -> tuple[float, float] | None:
        """Effective (x pu, capacity MW) of a corridor, or None when it is open or fully out."""
        if cid in self.open_corridors:
            return None
        c = network.corridors[cid]
        if c.a in self.blackout_areas or c.b in self.blackout_areas:
            return None
        return c.effective(self.out_lines)


def operating_points() -> dict[str, dict[str, Any]]:
    return load_params("operating_points")["operating_points"]


def build_state(network: ReducedNetwork, op_id: str, physics: Physics | None = None) -> GridState:
    """Balanced state of the network at an operating point."""
    physics = physics or Physics.load()
    ops = operating_points()
    if op_id not in ops:
        raise UnknownOperatingPointError(op_id)
    op = ops[op_id]
    order = network.order
    load = _split_demand(network, float(value(op["total_load_mw"])), value(op["zone_demand_share"]))
    gen = _dispatch(network, load, value(op["capacity_factor"]), physics.sync_techs)
    if "transfer" in op:
        _shift_transfer(network, gen, load, value(op["transfer"]), physics.sync_techs)
    kinetic = {a: sum(physics.inertia_h.get(t, 0.0) * mw for t, mw in gen[a].items()) for a in order}
    reserve = {a: physics.reserve_share for a in order}
    state = GridState(
        operating_point=op_id,
        load_mw=load,
        served_mw=dict(load),
        gen_mw=gen,
        tripped_mw={a: {} for a in order},
        kinetic_mws=kinetic,
        h_phys=dict(physics.inertia_h),
        reserve_share=reserve,
        sync_techs=physics.sync_techs,
        provenance=tuple(collect_provenance(op, f"operating_points.{op_id}")),
    )
    if "kinetic_energy_gvas" in op:
        _scale_inertia(state, order, float(value(op["kinetic_energy_gvas"])))
    sides = _sides(network, value(op["transfer"])) if "transfer" in op else {}
    for side, target in (value(op.get("kinetic_energy_gvas_by_side", {"value": {}})) or {}).items():
        _scale_inertia(state, sides[side], float(target))
    for side, target in (value(op.get("primary_reserve_mw_by_side", {"value": {}})) or {}).items():
        sync = sum(state.sync_gen(a) for a in sides[side])
        for a in sides[side]:
            state.reserve_share[a] = float(target) / sync if sync else 0.0
    return state


def _split_demand(network: ReducedNetwork, total: float, shares: dict[str, float]) -> dict[str, float]:
    present = {z: s for z, s in shares.items() if network.zone_areas(z)}
    norm = sum(present.values()) or 1.0
    out = {a: 0.0 for a in network.order}
    for zone, share in present.items():
        areas = network.zone_areas(zone)
        pop = sum(network.areas[a].population for a in areas)
        for a in areas:
            w = network.areas[a].population / pop if pop else 1.0 / len(areas)
            out[a] = round(total * share / norm * w, 3)
    return out


def _dispatch(
    network: ReducedNetwork, load: dict[str, float], cf: dict[str, float], sync: frozenset[str]
) -> dict[str, dict[str, float]]:
    gen = {
        a: {t: network.areas[a].installed_mw[t] * cf.get(t, 0.0) for t in network.areas[a].installed_mw}
        for a in network.order
    }
    total_load = sum(load.values())
    ren = sum(mw for g in gen.values() for t, mw in g.items() if t not in sync)
    sync_avail = sum(mw for g in gen.values() for t, mw in g.items() if t in sync)
    sync_needed = max(total_load - ren, MIN_SYNC_SHARE * total_load)
    k_sync = sync_needed / sync_avail if sync_avail else 0.0
    ren_target = total_load - sync_needed
    k_ren = ren_target / ren if ren else 0.0
    return {
        a: {t: round(mw * (k_sync if t in sync else k_ren), 3) for t, mw in g.items() if mw > 0}
        for a, g in gen.items()
    }


def _sides(network: ReducedNetwork, transfer: dict[str, Any]) -> dict[str, list[str]]:
    cut = network.areas[transfer["north"]].index
    return {
        "north": [a for a in network.order if network.areas[a].index <= cut],
        "south": [a for a in network.order if network.areas[a].index > cut],
    }


def _scale_side(
    gen: dict[str, dict[str, float]], areas: list[str], techs: frozenset[str], delta: float
) -> float:
    """Add `delta` MW to the given technologies of a side, pro rata. Returns what could not be placed."""
    base = sum(mw for a in areas for t, mw in gen[a].items() if t in techs)
    if base <= 0:
        return delta
    k = max(0.0, 1.0 + delta / base)
    for a in areas:
        for t in list(gen[a]):
            if t in techs:
                gen[a][t] = round(gen[a][t] * k, 3)
    return delta - base * (k - 1.0)


def _shift_transfer(
    network: ReducedNetwork,
    gen: dict[str, dict[str, float]],
    load: dict[str, float],
    transfer: dict[str, Any],
    sync: frozenset[str],
) -> None:
    """Move dispatch between the two sides until the north exports `transfer.mw`."""
    sides = _sides(network, transfer)
    export = sum(sum(gen[a].values()) - load[a] for a in sides["north"])
    delta = float(transfer["mw"]) - export
    _scale_side(gen, sides["north"], sync, delta)
    _scale_side(gen, sides["south"], sync, -delta)


def _scale_inertia(state: GridState, areas: list[str], target_gvas: float) -> None:
    """Match a published kinetic energy: online units carry more inertia than their dispatch
    suggests (committed, part-loaded machines)."""
    current = sum(state.kinetic_mws[a] for a in areas) / 1000.0
    if current <= 0:
        return
    k = target_gvas / current
    for a in areas:
        state.kinetic_mws[a] *= k
