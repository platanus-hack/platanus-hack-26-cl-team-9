"""Cascade engine (docs/stack.md 4.3): apply a disturbance, separate weak links, form islands,
run the island frequency model, and leave the post-transient quasi-steady state.

1. Apply the changes at t = 0 (open corridors, lines or substations, trip generation, disable
   defences, lose remote dispatch, step load).
2. DC flow with the post-event injections. A corridor above 120 % of capacity is a weak link: the
   most loaded one opens (ties together), at the north defence scheme time when it covers that
   corridor, else at the weak-link time. Repeat, at most 20 iterations (`truncated` otherwise).
3. Each island runs the frequency model. The pre-event flow of a weak link keeps feeding its
   island until the link opens.
4. Islands that collapse lose all load. Surviving islands keep their load shedding, curtailment
   and reserve pickup; overloads after ~2 s are labelled "thermal overload" and trip nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cascadasen.domain.events import make_event
from cascadasen.domain.simulation.defenses import DefenseSet, documented_trips_25f
from cascadasen.domain.simulation.frequency import (
    Coupling,
    IslandInput,
    IslandTrace,
    Ramp,
    simulate_island,
    steady_trace,
)
from cascadasen.domain.simulation.grid import GridState, Physics
from cascadasen.domain.simulation.network import ReducedNetwork
from cascadasen.domain.simulation.powerflow import dc_flow, islands

CHANGE_KINDS = (
    "open_corridor",
    "lines_out",
    "node_out",
    "trip_gen",
    "group_out",
    "renewable_drop",
    "disable_defense",
    "no_reserve",
    "load_step",
)


class ChangeError(ValueError):
    """A change cannot be applied to this network (unknown target, bad parameters)."""


@dataclass(frozen=True)
class Change:
    kind: str
    target: str
    mw: float | None = None
    share: float | None = None
    tech: str | None = None
    lines: tuple[str, ...] = ()


@dataclass
class IslandResult:
    id: str
    areas: list[str]
    result: str
    uncertain: bool
    trace: IslandTrace
    documented_collapse: bool = False

    def summary(self) -> dict[str, Any]:
        t = self.trace
        shown = "uncertain" if self.uncertain else self.result
        return {
            "id": self.id,
            "result": shown,
            "nodes": self.areas,
            "f_min_hz": t.f_min,
            "f_max_hz": t.f_max,
            "f_end_hz": t.f_end,
            "t_f_min_s": t.t_f_min,
            "rocof_hz_s": t.rocof_initial,
            "load_shed_mw": t.shed_mw,
            "curtailed_mw": t.curtailed_mw,
            "blackout_t_s": t.blackout_t,
            "documented_collapse": self.documented_collapse,
        }


@dataclass
class TransientResult:
    state: GridState
    islands: list[IslandResult]
    events: list[dict[str, Any]]
    pre_flows: dict[str, float]
    post_flows: dict[str, float]
    initial_open: list[str]
    weak_links: list[tuple[str, float]]
    truncated: bool
    load_shed_mw: float
    load_lost_mw: float
    people_without_power: float
    pre_state: GridState
    island_of_area: dict[str, str] = field(default_factory=dict)

    @property
    def disturbed(self) -> bool:
        return bool(self.events)


def _trip(state: GridState, area: str, mw: float, tech: str | None = None) -> float:
    """Trip up to `mw` of online generation in an area (one technology or pro rata). Returns MW tripped."""
    gens = state.gen_mw.get(area, {})
    pool = {t: g for t, g in gens.items() if (tech is None or t == tech) and g > 0}
    total = sum(pool.values())
    if total <= 0 or mw <= 0:
        return 0.0
    k = min(1.0, mw / total)
    for t, g in pool.items():
        cut = g * k
        gens[t] = round(g - cut, 3)
        state.remove_inertia(area, t, cut)
        state.tripped_mw.setdefault(area, {})
        state.tripped_mw[area][t] = round(state.tripped_mw[area].get(t, 0.0) + cut, 3)
    return total * k


def _area_of(network: ReducedNetwork, target: str) -> str:
    r = network.resolve(target)
    if r.area is None:
        raise ChangeError(f"{target}: se esperaba un área o una subestación")
    return r.area


def apply_change(network: ReducedNetwork, state: GridState, ch: Change, events: list, opened: list) -> None:
    """Mutate `state` with one change and record its timeline event at t = 0."""
    if ch.kind == "open_corridor":
        state.open_corridors.add(ch.target)
        opened.append(ch.target)
        events.append(make_event(0.0, "line_cut", [ch.target], "line_cut"))
    elif ch.kind == "lines_out":
        state.out_lines |= set(ch.lines)
        events.append(make_event(0.0, "line_cut", list(ch.lines), "line_cut"))
    elif ch.kind == "node_out":
        _node_out(network, state, ch.target, events)
    elif ch.kind == "trip_gen":
        r = network.resolve(ch.target)
        if r.kind == "node":
            node = network.nodes[ch.target]
            mw = ch.mw if ch.mw is not None else _node_online(network, state, ch.target)
            tripped = _trip(state, node.area, mw, ch.tech)
            area = node.area
        else:
            area = _area_of(network, ch.target)
            mw = ch.mw if ch.mw is not None else (ch.share or 0.25) * _online(state, area, ch.tech)
            tripped = _trip(state, area, mw, ch.tech)
        events.append(make_event(0.0, "plant_trip", [area], "plant_trip", mw=round(tripped, 1), tech=ch.tech))
    elif ch.kind in ("group_out", "renewable_drop"):
        areas = network.zone_areas(ch.target) or [_area_of(network, ch.target)]
        share = ch.share if ch.share is not None else 0.4
        tripped = sum(_trip(state, a, share * _online(state, a, ch.tech), ch.tech) for a in areas)
        key = "group_out" if ch.kind == "group_out" else "renewable_drop"
        events.append(
            make_event(
                0.0, "plant_trip", areas, key, mw=round(tripped, 1), tech=ch.tech, share=share, zone=ch.target
            )
        )
    elif ch.kind == "disable_defense":
        state.disabled_defenses.add(ch.target)
        events.append(make_event(0.0, "defense_disabled", [ch.target], "defense_disabled"))
    elif ch.kind == "no_reserve":
        area = _area_of(network, ch.target)
        state.no_reserve_areas.add(area)
        events.append(make_event(0.0, "control_lost", [area], "control_lost"))
    elif ch.kind == "load_step":
        areas = network.zone_areas(ch.target) or [_area_of(network, ch.target)]
        added = 0.0
        for a in areas:
            d = ch.mw / len(areas) if ch.mw is not None else (ch.share or 0.05) * state.load_mw[a]
            state.load_mw[a] += d
            state.served_mw[a] += d
            added += d
        events.append(make_event(0.0, "documented_event", areas, "demand_surge", mw=round(added, 1)))
    else:
        raise ChangeError(f"tipo de cambio desconocido: {ch.kind}")


def _online(state: GridState, area: str, tech: str | None) -> float:
    gens = state.gen_mw.get(area, {})
    return gens.get(tech, 0.0) if tech else sum(gens.values())


def _node_online(network: ReducedNetwork, state: GridState, node_id: str) -> float:
    """Online MW of the plants at one substation, at the area's dispatch ratio per technology."""
    node = network.nodes[node_id]
    inst = network.areas[node.area].installed_mw
    gens = state.gen_mw.get(node.area, {})
    return sum(
        mw * (gens.get(t, 0.0) / inst[t] if inst.get(t) else 0.0) for t, mw in node.generation_mw.items()
    )


def _node_out(network: ReducedNetwork, state: GridState, node_id: str, events: list) -> None:
    if node_id not in network.nodes:
        raise ChangeError(f"{node_id}: subestación desconocida")
    node = network.nodes[node_id]
    area = network.areas[node.area]
    state.out_nodes.add(node_id)
    state.out_lines |= set(node.corridor_lines)
    lost = state.load_mw[node.area] * node.population / area.population if area.population else 0.0
    lost = min(lost, state.served_mw[node.area])
    state.served_mw[node.area] -= lost
    inst = area.installed_mw
    tripped = 0.0
    for tech, mw in node.generation_mw.items():
        online = state.gen_mw.get(node.area, {}).get(tech, 0.0)
        ratio = online / inst[tech] if inst.get(tech) else 0.0
        tripped += _trip(state, node.area, mw * ratio, tech)
    events.append(
        make_event(
            0.0,
            "line_cut",
            list(node.corridor_lines) or [node_id],
            "substation_out",
            node=node_id,
            name=node.name,
            load_lost_mw=round(lost, 1),
            gen_tripped_mw=round(tripped, 1),
        )
    )


def _pdce_corridors(network: ReducedNetwork, defenses: DefenseSet) -> set[str]:
    pair = {defenses.pdce_north, defenses.pdce_south}
    return {cid for cid, c in network.corridors.items() if {c.a, c.b} == pair}


def _separate_weak_links(
    network: ReducedNetwork, post: GridState, defenses: DefenseSet, physics: Physics, events: list
) -> tuple[list[tuple[str, float]], bool]:
    pdce = _pdce_corridors(network, defenses)
    weak: list[tuple[str, float]] = []
    for _ in range(physics.max_iterations):
        flows = dc_flow(network, post)
        over = []
        for cid, f in flows.items():
            eff = post.corridor(network, cid)
            if eff and abs(f) > physics.overload_ratio * eff[1]:
                over.append((cid, abs(f) / eff[1], f))
        if not over:
            return weak, False
        worst = max(r for _, r, _ in over)
        for cid, ratio, f in over:
            if ratio < worst * 0.99:
                continue
            t_trip = (
                defenses.pdce_t_sep_s
                if cid in pdce and defenses.pdce_enabled(post.disabled_defenses)
                else defenses.weak_link_trip_s
            )
            post.open_corridors.add(cid)
            weak.append((cid, t_trip))
            events.append(
                make_event(
                    t_trip,
                    "line_overload_open",
                    [cid],
                    "weak_link_separation",
                    loading_pct=round(ratio * 100),
                    flow_mw=round(f, 1),
                )
            )
    return weak, True


def _island_input(
    iid: str,
    areas: list[str],
    network: ReducedNetwork,
    post: GridState,
    pre_flows: dict[str, float],
    weak: list[tuple[str, float]],
    defenses: DefenseSet,
    ramps: list[Ramp],
) -> IslandInput:
    members = set(areas)
    couplings = []
    for cid, t_trip in weak:
        c = network.corridors[cid]
        f = pre_flows.get(cid, 0.0)
        if c.a in members and c.b not in members:
            couplings.append(Coupling(cid, t_trip, -f))
        elif c.b in members and c.a not in members:
            couplings.append(Coupling(cid, t_trip, f))
    load = sum(post.served_mw[a] for a in areas)
    disabled = post.disabled_defenses
    edac_load = sum(
        post.served_mw[a] for a in areas if defenses.zone_edac_enabled(network.areas[a].zone, disabled)
    )
    extreme = 0.0
    if "extreme_edac" not in disabled:
        for zone, mw in defenses.extreme_mw_by_zone.items():
            zone_areas = network.zone_areas(zone)
            zone_load = sum(post.served_mw[a] for a in zone_areas)
            here = sum(post.served_mw[a] for a in zone_areas if a in members)
            if zone_load > 0 and defenses.zone_edac_enabled(zone, disabled):
                extreme += mw * here / zone_load
    gen = sum(post.gen(a) for a in areas)
    sync = sum(post.sync_gen(a) for a in areas)
    h_trip = (
        sum(
            post.h_phys.get(t, 0.0) * mw
            for a in areas
            for t, mw in post.gen_mw[a].items()
            if t in post.sync_techs
        )
        / sync
        if sync > 0
        else 0.0
    )
    return IslandInput(
        id=iid,
        areas=areas,
        gen_mw=gen,
        sync_mw=sync,
        nonsync_mw=gen - sync,
        load_mw=load,
        kinetic_mws=sum(post.inertia_mws(a) for a in areas),
        reserve_mw=sum(post.reserve_mw(a) for a in areas),
        battery_mw=sum(post.battery_mw.get(a, 0.0) for a in areas),
        couplings=couplings,
        ramps=ramps,
        edac_share=edac_load / load if load > 0 else 0.0,
        extreme_mw=extreme,
        lfsm="lfsm_o" not in disabled,
        h_trip_s=h_trip,
    )


def _settle_island(post: GridState, areas: list[str], trace: IslandTrace) -> None:
    """Apply a surviving island's shedding, curtailment and lost generation, then rebalance it with
    the primary reserve (secondary control brings frequency back to nominal)."""
    served = sum(post.served_mw[a] for a in areas)
    if served > 0 and trace.shed_mw > 0:
        k = max(0.0, 1.0 - trace.shed_mw / served)
        for a in areas:
            post.served_mw[a] *= k
    for amount, sync_only in ((trace.curtailed_mw, False), (trace.lost_mw, True)):
        if amount <= 0:
            continue
        pool = {a: (post.sync_gen(a) if sync_only else post.gen(a) - post.sync_gen(a)) for a in areas}
        total = sum(pool.values())
        for a in areas:
            if total > 0 and pool[a] > 0:
                techs = [t for t in post.gen_mw[a] if (t in post.sync_techs) == sync_only]
                share = amount * pool[a] / total
                for t in techs:
                    _trip(post, a, share * post.gen_mw[a][t] / pool[a], t)
    residual = sum(post.served_mw[a] for a in areas) - sum(post.gen(a) for a in areas)
    reserve = {a: post.reserve_mw(a) for a in areas}
    avail = sum(reserve.values())
    pickup = max(0.0, min(residual, avail))
    for a in areas:
        if avail > 0 and pickup > 0:
            share = pickup * reserve[a] / avail
            sync = post.sync_gen(a)
            if sync > 0:
                for t in post.gen_mw[a]:
                    if t in post.sync_techs:
                        post.gen_mw[a][t] += share * post.gen_mw[a][t] / sync
            post.reserve_used_mw[a] = post.reserve_used_mw.get(a, 0.0) + share
    unmet = residual - pickup
    if unmet > 1.0:  # deficit beyond the reserve: the rest stays unserved
        served = sum(post.served_mw[a] for a in areas)
        k = max(0.0, 1.0 - unmet / served) if served else 0.0
        for a in areas:
            post.served_mw[a] *= k
    elif residual < -1.0:  # surplus: synchronous units back down
        surplus = -residual
        sync_total = sum(post.sync_gen(a) for a in areas)
        for a in areas:
            sync = post.sync_gen(a)
            if sync_total > 0 and sync > 0:
                for t in post.gen_mw[a]:
                    if t in post.sync_techs:
                        post.gen_mw[a][t] -= min(post.gen_mw[a][t], surplus * post.gen_mw[a][t] / sync_total)


def _collapse(post: GridState, areas: list[str]) -> None:
    for a in areas:
        post.blackout_areas.add(a)
        post.served_mw[a] = 0.0
        _trip(post, a, post.gen(a))


def run_transient(
    network: ReducedNetwork,
    state: GridState,
    changes: list[Change],
    defenses: DefenseSet,
    physics: Physics,
    *,
    behavior: str = "per_code",
    scenario: str | None = None,
    full: bool = True,
) -> TransientResult:
    pre_flows = dc_flow(network, state)
    post = state.copy()
    events: list[dict[str, Any]] = []
    opened: list[str] = []
    for ch in changes:
        apply_change(network, post, ch, events, opened)
    weak, truncated = _separate_weak_links(network, post, defenses, physics, events)
    comps = islands(network, post)
    if len(comps) > 1 and (weak or opened):
        t_form = max([0.0, *(t for _, t in weak)])
        events.append(
            make_event(
                t_form,
                "island_formed",
                [f"I{k + 1}" for k in range(len(comps))],
                "island_formed",
                count=len(comps),
            )
        )

    ramps: list[Ramp] = []
    if behavior == "as_happened" and scenario == "25F":
        trips, _ = documented_trips_25f()
        ramps = [Ramp(d["start_s"], d["end_s"], d["mw"], d["label_key"]) for d in trips]
        for r in ramps:
            events.append(make_event(r.start, "documented_event", [], r.label_key, mw=r.mw, until_s=r.end))

    pdce = _pdce_corridors(network, defenses)
    lost_pdce = pdce & (set(opened) | {c for c, _ in weak})
    flow_ns = sum(pre_flows.get(c, 0.0) for c in pdce)
    out_of_range = (
        bool(lost_pdce)
        and scenario != "25F"
        and (flow_ns > defenses.pdce_limit_ns_mw or flow_ns < -defenses.pdce_limit_sn_mw)
    )

    results: list[IslandResult] = []
    island_of: dict[str, str] = {}
    for k, areas in enumerate(comps):
        iid = f"I{k + 1}"
        for a in areas:
            island_of[a] = iid
        island_ramps = ramps if defenses.pdce_south in areas else []
        inp = _island_input(iid, areas, network, post, pre_flows, weak, defenses, island_ramps)
        disturbed = abs(inp.gen_mw - inp.load_mw) > 1.0 or inp.couplings or inp.ramps
        trace = (
            simulate_island(inp, defenses, physics, full) if disturbed else steady_trace(inp, physics, full)
        )
        uncertain = out_of_range and bool({defenses.pdce_north, defenses.pdce_south} & set(areas))
        results.append(IslandResult(iid, areas, trace.result, uncertain, trace))

    for r in results:
        if r.result in ("blackout", "local_cut", "no_load"):
            _collapse(post, r.areas)
            kind = "island_blackout"
            events.append(make_event(r.trace.blackout_t or 0.0, kind, [r.id], r.result, nodes=r.areas))
        else:
            _settle_island(post, r.areas, r.trace)
            if r.trace.f_min < physics.f0 - 0.05 or r.trace.f_max > physics.f0 + 0.05:
                events.append(
                    make_event(
                        physics.horizon,
                        "island_stable",
                        [r.id],
                        "island_stable",
                        f_end_hz=r.trace.f_end,
                        nodes=r.areas,
                    )
                )
        for s in r.trace.shed_events:
            events.append(make_event(s.t, "load_shed", [r.id], s.label_key, mw=s.mw, step=s.step))

    if behavior == "as_happened" and scenario == "25F":
        north = next((r for r in results if defenses.pdce_north in r.areas and r.result == "maintains"), None)
        if north:  # the north's later collapse is documented, not computed (idea.md 6)
            north.documented_collapse = True
            _collapse(post, north.areas)
            events.append(
                make_event(
                    physics.horizon,
                    "documented_event",
                    [north.id],
                    "north_collapse_documented",
                    nodes=north.areas,
                )
            )

    post_flows = dc_flow(network, post)
    for cid, f in post_flows.items():
        eff = post.corridor(network, cid)
        if eff and abs(f) > eff[1]:
            events.append(
                make_event(
                    physics.weak_link_window,
                    "documented_event",
                    [cid],
                    "thermal_overload",
                    loading_pct=round(abs(f) / eff[1] * 100),
                    flow_mw=round(f, 1),
                )
            )
    events.sort(key=lambda e: e["t"])  # stable: causes stay before their consequences

    shed = sum(r.trace.shed_mw for r in results if r.result == "maintains")
    lost = sum(state.served_mw.values()) - sum(post.served_mw.values())
    people = sum(
        network.areas[a].population * (1.0 - post.served_mw[a] / post.load_mw[a])
        for a in network.order
        if post.load_mw[a] > 0
    )
    return TransientResult(
        state=post,
        islands=results,
        events=events,
        pre_flows=pre_flows,
        post_flows=post_flows,
        initial_open=opened,
        weak_links=weak,
        truncated=truncated,
        load_shed_mw=round(shed, 1),
        load_lost_mw=round(max(0.0, lost), 1),
        people_without_power=round(max(0.0, people)),
        pre_state=state,
        island_of_area=island_of,
    )
