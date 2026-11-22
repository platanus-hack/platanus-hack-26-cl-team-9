"""Prepare a stressed scenario: more people, more demand, less generation or weaker lines (docs/stress.md).

Why: the team builds scenarios where a place grows or a technology drops ("halve every hydro plant") and then
simulates failures on them. This module only prepares the grid: it resolves the filters into per-bus and per-line
values and reports the prepared state with no failure. The cascade of a failure still runs in the existing
processes (`/grids/simulate`, `/grids/dependency`, `/grids/cost`), which take the same `changes`. Each request
carries every change, like the cuts: nothing is stored, and loading a scenario or a benchmark starts clean.
Population drives demand (only the part that grows with people, `stress.regulated_share`). The island's
synchronous units redispatch the imbalance (the grid tries to survive).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any, cast

import numpy as np

from cascadasen.application.grids import GridError
from cascadasen.application.places import resolve_place
from cascadasen.domain.cascade.engine import CascadeParams
from cascadasen.domain.cascade.flow import dc_flow, find_islands
from cascadasen.domain.cascade.frequency import cascade_params
from cascadasen.domain.cascade.health import prefault_health
from cascadasen.domain.cascade.overlay import BALANCE_RULE, DEFAULT_INERTIA_H, MAX_INERTIA_H
from cascadasen.domain.cascade.scenario import OperatingPoint, _nearest_bus_per_node
from cascadasen.domain.cascade.tracing import dependency_workflow
from cascadasen.domain.geo import haversine_km
from cascadasen.domain.simulation.params import value
from cascadasen.domain.theater.areas import bus_id

MAX_CHANGES = 20
MAX_FACTOR = 5.0
TARGETS = ("population", "demand", "generation", "lines", "substation")
MAX_SUBSTATIONS = 5
SUBSTATION_OFFSET_DEG = 0.03  # ~3 km: a new substation sits next to the one that serves its place
MAX_NEIGHBOUR_KM = 150.0
# PyPSA-CL carriers of the dispatch (baseline_opf.json) to the plant technologies of the snapshot.
CARRIER_TECH = {
    "solar PV": "solar",
    "CSP": "solar",
    "onshore wind": "eolica",
    "hydro ROR": "hidro",
    "hydro reservoir": "hidro",
    "gas": "gas",
    "coal": "carbon",
    "diesel": "diesel",
    "biofuel": "bioenergia",
    "geothermal": "geotermica",
}
TECH_NOTE = (
    "La generación de cada barra se reparte por tecnología según la potencia instalada de sus plantas por el "
    "factor de despacho nacional de esa tecnología en el punto (supuesto: el despacho viene sumado por barra). "
    "La térmica se separa en carbón, gas y diésel por el primer combustible de la planta; `termica` agrupa las tres."
)


def prepare_workflow(world, point: str, changes: list[dict]) -> dict:
    """The prepared scenario with no failure: what each change touches, the overlay values to send back with a
    simulation, lines the prepared grid already loads over their limit, and whom each generator should feed."""
    from cascadasen.application.grid_simulation import prepare_edits  # grid_simulation imports this module

    ctx = _context(world, point)
    edit = _apply_changes(ctx, changes, detail=True)
    prepared, _, _, _ = prepare_edits(world, point, [], [], allow_empty=True, changes=changes)
    edited = prepared
    return {
        "point": point,
        "changes": edit.report,
        "per_capita_w": round(ctx.per_capita_w, 1),
        "totals": _prepared_totals(edited.point),
        "overloaded_lines": _overloaded(edited.net, edited.point),
        "should_feed": _should_feed(ctx, edited.net, edited.point),
        "redispatch": edited.balance,
        "warnings": edited.warnings,
        # health index of the prepared grid before any failure (no N-1 sweep: one request stays fast)
        "health": prefault_health(edited.net, edited.point, with_n1=False).as_dict(),
        "assumptions": _assumptions(ctx)
        + (
            [{"id": "new_plant", "text": NEW_PLANT_NOTE, "is_assumption": True}]
            if any(r.get("new_plant") for r in edit.report)
            else []
        ),
    }


def scenario_overrides(world, point: str, changes: list[dict]) -> tuple[dict, np.ndarray]:
    """Overlay overrides and the people per bus of the prepared scenario, for `prepare_edits`."""
    ctx = _context(world, point)
    edit = _apply_changes(ctx, changes)
    return edit.overrides(ctx), edit.people


def supply_workflow(world, point: str, prepared, edited, state) -> dict:
    """After a failure: per generating substation, the people it should feed on the prepared grid before the
    failure against the people it still feeds once the cascade settled, with the percentage. People at a
    substation taken out of service count as not fed. Ordered by id, never by damage (docs/cyber.md section 8.2),
    and added up per zone."""
    ctx = _context(world, point)
    before = prepared.point
    n = len(before.load)
    after_load = state.load[:n]
    served = np.divide(after_load, before.load, out=np.ones_like(before.load), where=before.load > 0)
    should = dependency_workflow(prepared.net, before.gen, before.load, before.people)
    people_after = np.concatenate([before.people * served, np.zeros(len(state.load) - n)])
    feeds = {
        r["bus"]: r["people_fed"]
        for r in dependency_workflow(
            edited.net, state.gen, state.load, people_after, frozenset(state.open_lines)
        )
    }
    rows = [
        _source_row(ctx, prepared.net, r["bus"], r["people_fed"], feeds.get(r["bus"], 0), before, state.gen)
        for r in should
    ]
    rows.sort(key=lambda r: r["id"])
    return {"sources": rows, "by_zone": _by_zone(rows)}


@dataclass
class _Context:
    net: Any  # TheaterNetwork
    op: OperatingPoint
    names: list[str]
    zone: list[str]
    area: list[str]
    node_bus: dict[str, int]
    comunas: dict[str, dict]  # cut and lower-case name -> comuna
    tech_share: np.ndarray  # bus x TECH_ORDER, rows sum 1 where the bus generates and has known plants
    per_capita_w: float
    regulated_share: float


# Thermal plants split by their first fuel; `termica` is a tag for all of them. Fuel unknown (cogeneration, "S/I",
# 22 MW): only under `termica`, with no dispatch of its own.
THERMAL = ("carbon", "diesel", "gas", "termica_otra")
# `bateria` has no plants in the dispatch: it only exists as new capacity (`add` at a place), injecting its MW
# through an inverter, with no inertia (assumption: discharging at full power at the operating point).
TECH_ORDER = ("bioenergia", "eolica", "geotermica", "hidro", "solar", *THERMAL, "bateria")
TAGS = {"termica": THERMAL}
SYNC_TECH = frozenset({"bioenergia", "geotermica", "hidro", *THERMAL})
NEW_PLANT_NOTE = (
    "Una central nueva (donde la barra no tenía esa tecnología) inyecta sus MW en la barra elegida; si es "
    "sincrónica aporta inercia con H = 4 s y una batería inyecta a plena potencia sin inercia (supuestos)."
)
FUEL_TECH = (
    ("CARBON", "carbon"),
    ("PETCOKE", "carbon"),
    ("GAS", "gas"),
    ("PROPANO", "gas"),
    ("PETROLEO", "diesel"),
    ("FUEL OIL", "diesel"),
)


def _load_point(world, point: str):
    try:
        return world.load(point)
    except KeyError as exc:
        raise GridError("not_found", f"No existe el punto de operación: {point}") from exc


def _plant_tech(plant: dict) -> str | None:
    if plant.get("tech") != "termica":
        return plant.get("tech") if plant.get("tech") in TECH_ORDER else None
    fuel = str(plant.get("fuel") or "").upper()
    return next((tech for key, tech in FUEL_TECH if fuel.startswith(key)), "termica_otra")


def stress_context(world, point: str) -> _Context:
    """The cached context of a point, for resolving places outside a change (`GET /grids/places`)."""
    return _context(world, point)


@cache  # per world and point: the filters and shares do not change between requests
def _context(world, point: str) -> _Context:
    net, op = _load_point(world, point)
    snapshot, ops, opf = _documents(str(world.processed))
    node_bus = _nearest_bus_per_node(net.buses, snapshot)
    share = float(value(cascade_params()["stress"]["regulated_share"]))
    comunas = {}
    for c in snapshot["comunas"]:
        comunas[c["cut"]] = c
        comunas[c["name"].strip().lower()] = c
    return _Context(
        net=net,
        op=op,
        names=list(net.buses.names),
        zone=[net.areas[a].zone for a in net.area_of_bus],
        area=list(net.area_of_bus),
        node_bus=node_bus,
        comunas=comunas,
        tech_share=_tech_share(net.buses, snapshot, ops, opf, point, node_bus),
        per_capita_w=share * float(op.load.sum()) * 1e6 / max(float(op.people.sum()), 1.0),
        regulated_share=share,
    )


@cache
def _documents(processed: str) -> tuple[dict, dict, dict]:
    root = Path(processed)
    return tuple(
        json.loads((root / name).read_text(encoding="utf-8"))
        for name in ("grid_snapshot.json", "operating_points.json", "baseline_opf.json")
    )


def _tech_share(
    net, snapshot: dict, ops: dict, opf: dict, point: str, node_bus: dict[str, int]
) -> np.ndarray:
    """Share of each technology in each bus's dispatch: installed MW x the national dispatch factor of the point."""
    cap = np.zeros((net.size, len(TECH_ORDER)))
    for p in snapshot["plants"]:
        tech = _plant_tech(p) if p.get("operating") else None
        bus = _plant_bus(p, ops["plant_bus"], net, node_bus) if tech else None
        if bus is not None:
            cap[bus, TECH_ORDER.index(tech)] += float(p["mw"])
    dispatched = np.zeros(len(TECH_ORDER))
    carriers = next(x for x in opf["points"] if x["id"] == point)["gen_by_carrier_mw"]
    for carrier, mw in carriers.items():
        if carrier in CARRIER_TECH:
            dispatched[TECH_ORDER.index(CARRIER_TECH[carrier])] += mw
    factor = np.divide(dispatched, cap.sum(axis=0), out=np.zeros_like(dispatched), where=cap.sum(axis=0) > 0)
    weight = cap * factor
    total = weight.sum(axis=1, keepdims=True)
    return np.divide(weight, total, out=np.zeros_like(weight), where=total > 0)


def _plant_bus(plant: dict, plant_bus: dict, net, node_bus: dict[str, int]) -> int | None:
    model_bus = plant_bus.get(plant["id"])
    if model_bus in net.bus_of_model_bus:
        return net.bus_of_model_bus[model_bus]
    return node_bus.get(cast(str, plant.get("node")))


# ---- changes ----------------------------------------------------------------------------------


@dataclass
class _Edit:
    people: np.ndarray
    load: np.ndarray
    gen: np.ndarray
    sync: np.ndarray
    inertia: np.ndarray
    lines: dict[str, dict] = field(default_factory=dict)  # R### -> {capacity_mw, x_pu}
    report: list[dict] = field(default_factory=list)

    def overrides(self, ctx: _Context) -> dict:
        """Overlay overrides for the buses and lines that changed. Generation is only set where it changed,
        because a bus whose generation the overlay sets takes no share of the redispatch."""
        op, buses = ctx.op, {}
        for i in range(len(self.load)):
            rec = {}
            if abs(self.load[i] - op.load[i]) > 1e-6:
                rec["load_mw"] = round(float(self.load[i]), 2)
            if abs(self.gen[i] - op.gen[i]) > 1e-6:
                rec["gen_mw"] = round(float(self.gen[i]), 2)
            if abs(self.sync[i] - op.sync_mw[i]) > 1e-6:
                sync = round(float(min(self.sync[i], self.gen[i])), 2)
                rec |= {
                    "sync_mw": sync,
                    "inertia_mws": min(round(float(self.inertia[i]), 2), MAX_INERTIA_H * sync),
                }
            if rec:
                buses[bus_id(i)] = rec
        return {"bus_overrides": buses, "line_overrides": self.lines}


def _apply_changes(ctx: _Context, changes: list[dict], detail: bool = False) -> _Edit:
    _check_changes(changes)
    op = ctx.op
    edit = _Edit(op.people.copy(), op.load.copy(), op.gen.copy(), op.sync_mw.copy(), op.inertia_mws.copy())
    new_substations = 0
    for k, raw in enumerate(changes):
        apply = {"population": _population, "demand": _demand, "generation": _generation, "lines": _lines}
        change, places = _resolve_places(ctx, raw, f"changes[{k}]")
        if change["target"] == "substation":
            entry = _substation_entry(
                _substation_spec(ctx, raw, f"changes[{k}]"), len(ctx.names) + new_substations
            )
            new_substations += 1
            entry["places"] = places
            edit.report.append({"target": "substation", **entry})
            continue
        entry = apply[change["target"]](ctx, edit, change, f"changes[{k}]")
        if places:
            entry["places"] = places
        if not detail:
            entry.pop("elements", None)
        edit.report.append({"target": change["target"], **entry})
    return edit


def _resolve_places(ctx: _Context, change: dict, where: str) -> tuple[dict, list[dict]]:
    """`places` (a comuna, a substation, a province, an area) become the one bus each resolves to, added to
    `buses`. The report keeps how each was resolved, so the caller sees where the point went."""
    if not change.get("places"):
        return change, []
    found = []
    for place in change["places"]:
        try:
            found.append(resolve_place(ctx, place))
        except GridError as exc:
            raise GridError(exc.kind, f"{where}: {exc}") from exc
    buses = list(dict.fromkeys([*(change.get("buses") or []), *(f["bus"] for f in found)]))
    return {**change, "buses": buses}, found


def _check_changes(changes: list[dict]) -> None:
    if not changes:
        raise GridError("invalid", "Indica al menos un cambio")
    if len(changes) > MAX_CHANGES:
        raise GridError("invalid", f"Máximo {MAX_CHANGES} cambios por request")
    if sum(c.get("target") == "substation" for c in changes) > MAX_SUBSTATIONS:
        raise GridError("invalid", f"Máximo {MAX_SUBSTATIONS} subestaciones nuevas por escenario")


def substation_specs(world, point: str, changes: list[dict]) -> list[dict]:
    """The overlay spec (`overlay.add_substation`) of each `substation` change, in order. Why: the stateless
    scenario path builds new substations from the same `changes` the web resends, so the map, the simulation and
    the assistant see one grid (docs/assistant.md)."""
    ctx = _context(world, point)
    return [
        _substation_spec(ctx, c, f"changes[{k}]")
        for k, c in enumerate(changes)
        if c.get("target") == "substation"
    ]


def _substation_spec(ctx: _Context, change: dict, where: str) -> dict:
    """A new substation next to the one that serves `places[0]`, at its voltage, linked to it and to the nearest
    other substation of that voltage (two paths: assumption, a single link would make it a dead end)."""
    try:
        anchor = int(resolve_place(ctx, change["places"][0])["bus"][1:])
    except GridError as exc:
        raise GridError(exc.kind, f"{where}: {exc}") from exc
    buses, kv = ctx.net.buses, float(ctx.net.buses.kv[anchor])
    near = sorted(
        (
            haversine_km(buses.lon[anchor], buses.lat[anchor], buses.lon[j], buses.lat[j]),
            j,
        )
        for j in range(buses.size)
        if j != anchor and abs(float(buses.kv[j]) - kv) < 1e-6
    )
    targets = [anchor] + [j for km, j in near[:1] if km <= MAX_NEIGHBOUR_KM]
    name = change.get("name") or f"S/E NUEVA {ctx.names[anchor].removeprefix('S/E ')}"
    spec: dict[str, Any] = {
        "name": name,
        "lat": change["lat"]
        if change.get("lat") is not None
        else float(buses.lat[anchor]) + SUBSTATION_OFFSET_DEG,
        "lon": change["lon"]
        if change.get("lon") is not None
        else float(buses.lon[anchor]) + SUBSTATION_OFFSET_DEG,
        "kv": kv,
        "connections": [{"to": bus_id(j)} for j in targets],
    }
    if change.get("load_mw"):
        spec["load"] = {"mw": change["load_mw"], "kind": "consumo"}
    if change.get("generator_mw"):
        spec["generator"] = {"mw": change["generator_mw"], "tech": change["tech"][0]}
    return spec


def _substation_entry(spec: dict, index: int) -> dict:
    """The report row of a new substation: where it is, its id and the buses it connects to."""
    return {
        "matched": 1,
        "new_substation": True,
        "connects_to": [c["to"] for c in spec["connections"]],
        "load_mw": spec.get("load", {}).get("mw"),
        "gen_mw": spec.get("generator", {}).get("mw"),
        "tech": [spec["generator"]["tech"]] if spec.get("generator") else None,
        "elements": [
            {k: spec[k] for k in ("name", "lat", "lon", "kv")} | {"id": bus_id(index)},
        ],
    }


def _population(ctx: _Context, edit: _Edit, change: dict, where: str) -> dict:
    """More (or fewer) people: by comuna through the substations that serve it, or by bus. Demand follows with the
    per-capita value of the point; the rest of the bus's demand (mining, industry) stays."""
    delta = _people_delta(ctx, edit, change, where)
    before = edit.load.copy()
    edit.people = _floored(edit.people, delta)
    edit.load = _floored(edit.load, delta * ctx.per_capita_w / 1e6)
    touched = np.flatnonzero(np.abs(delta) > 1e-9)
    return {
        "matched": len(touched),
        "people_delta": round(float(delta.sum())),
        "load_delta_mw": round(float((edit.load - before).sum()), 1),
        "elements": [_bus_row(ctx, i, before[i], edit.load[i], people=edit.people[i]) for i in touched],
    }


def _people_delta(ctx: _Context, edit: _Edit, change: dict, where: str) -> np.ndarray:
    delta = np.zeros(len(edit.people))
    if change.get("comunas"):
        for ref in change["comunas"]:
            comuna = _comuna(ctx, ref, where)
            pop = float(comuna["population"])
            grow = pop * (change["factor"] - 1.0) if change.get("factor") is not None else 0.0
            for s in comuna["served_by"]:
                if s["node"] in ctx.node_bus and pop > 0:
                    delta[ctx.node_bus[s["node"]]] += s["population"] / pop * grow
        if change.get("add") is not None:  # one total for every comuna named, split by their population
            comunas = [_comuna(ctx, ref, where) for ref in change["comunas"]]
            total = sum(float(c["population"]) for c in comunas) or 1.0
            for c in comunas:
                for s in c["served_by"]:
                    if s["node"] in ctx.node_bus:
                        delta[ctx.node_bus[s["node"]]] += change["add"] * s["population"] / total
        return delta
    buses = _buses(ctx, change, where)
    return _spread(edit.people, buses, change)


def _demand(ctx: _Context, edit: _Edit, change: dict, where: str) -> dict:
    """Demand changed alone (another hour, a new industry), with no change of population."""
    buses = _comuna_buses(ctx, change, where) if change.get("comunas") else _buses(ctx, change, where)
    before = edit.load.copy()
    edit.load = _floored(edit.load, _spread(edit.load, buses, change))
    touched = [i for i in buses if abs(edit.load[i] - before[i]) > 1e-9]
    return {
        "matched": len(touched),
        "load_delta_mw": round(float((edit.load - before).sum()), 1),
        "elements": [_bus_row(ctx, i, before[i], edit.load[i]) for i in touched],
    }


def _generation(ctx: _Context, edit: _Edit, change: dict, where: str) -> dict:
    """Generation of the buses (and technologies) the filter picks. Synchronous technologies move their
    synchronous MW and inertia with them."""
    techs = _techs(change, where)
    cols = [TECH_ORDER.index(t) for t in techs]
    buses = _buses(ctx, change, where)
    part = np.zeros(len(edit.gen))  # MW of the chosen technologies at each chosen bus
    sync_part = np.zeros(len(edit.gen))
    for i in buses:
        share = ctx.tech_share[i, cols].sum() if techs != TECH_ORDER else 1.0
        sync_share = sum(ctx.tech_share[i, TECH_ORDER.index(t)] for t in techs if t in SYNC_TECH)
        part[i] = edit.gen[i] * share
        sync_part[i] = edit.gen[i] * sync_share if techs != TECH_ORDER else edit.sync[i]
    if buses and (change.get("add") or 0) > 0 and not part[buses].any():
        return _new_plant(ctx, edit, change, where, techs, buses)
    delta = _spread(part, [i for i in buses if part[i] > 0], change)
    ratio = np.divide(sync_part, part, out=np.zeros_like(part), where=part > 0)
    before = edit.gen.copy()
    old_sync = edit.sync.copy()
    edit.gen = _floored(edit.gen, delta)
    edit.sync = np.clip(edit.sync + delta * ratio, 0.0, edit.gen)
    scaled = edit.inertia * np.divide(edit.sync, old_sync, out=np.ones_like(old_sync), where=old_sync > 0)
    # the overlay caps H at MAX_INERTIA_H; some base buses exceed it
    changed = np.abs(edit.sync - old_sync) > 1e-9
    edit.inertia = np.where(changed, np.minimum(scaled, MAX_INERTIA_H * edit.sync), edit.inertia)
    touched = np.flatnonzero(np.abs(edit.gen - before) > 1e-9)
    return {
        "matched": len(touched),
        "tech": list(techs),
        "gen_delta_mw": round(float((edit.gen - before).sum()), 1),
        "elements": [_bus_row(ctx, i, before[i], edit.gen[i], key="gen_mw") for i in touched],
    }


def _new_plant(
    ctx: _Context, edit: _Edit, change: dict, where: str, techs: tuple[str, ...], buses: list[int]
) -> dict:
    """`add` where none of the chosen buses has the technology: a new plant, split evenly over them. Before,
    `add` was spread by the current MW of the technology, so a solar plant at a bus with no solar added nothing
    and the answer still said 200 OK with `matched: 0`."""
    if techs == TECH_ORDER:
        raise GridError("invalid", f"{where}: una central nueva necesita su tecnología (tech)")
    sync = [t in SYNC_TECH for t in techs]
    if any(sync) and not all(sync):
        raise GridError(
            "invalid", f"{where}: una central nueva lleva una sola tecnología, o solo sincrónicas"
        )
    delta = _spread(np.zeros(len(edit.gen)), buses, change)  # nothing there yet: evenly
    before, old_sync = edit.gen.copy(), edit.sync.copy()
    edit.gen = edit.gen + delta
    if all(sync):
        edit.sync = edit.sync + delta
        edit.inertia = np.minimum(edit.inertia + delta * DEFAULT_INERTIA_H, MAX_INERTIA_H * edit.sync)
    touched = np.flatnonzero(np.abs(edit.gen - before) > 1e-9)
    return {
        "matched": len(touched),
        "tech": list(techs),
        "new_plant": True,
        "synchronous": all(sync),
        "gen_delta_mw": round(float((edit.gen - before).sum()), 1),
        "sync_delta_mw": round(float((edit.sync - old_sync).sum()), 1),
        "elements": [_bus_row(ctx, i, before[i], edit.gen[i], key="gen_mw") for i in touched],
    }


def _lines(ctx: _Context, edit: _Edit, change: dict, where: str) -> dict:
    """Capacity (`factor`) and reactance (`x_factor`: the DC flow uses reactance, not resistance) of the lines
    the filter picks: ids, voltage levels, or both ends inside the zones or areas."""
    picked = _pick_lines(ctx, change, where)
    rows = []
    for ln in picked:
        rec = edit.lines.setdefault(ln.id, {})
        cap, x = rec.get("capacity_mw", ln.capacity_mw), rec.get("x_pu", ln.x_pu)
        if change.get("factor") is not None:
            rec["capacity_mw"] = round(cap * change["factor"], 2)
        if change.get("x_factor") is not None:
            rec["x_pu"] = x * change["x_factor"]
        rows.append(
            {
                "id": ln.id,
                "kv": ln.kv,
                "capacity_mw": [round(cap, 1), round(rec.get("capacity_mw", cap), 1)],
                "x_pu": [round(x, 4), round(rec.get("x_pu", x), 4)],  # per unit: 2 decimals would read 0.01
            }
        )
    return {"matched": len(picked), "elements": rows}


# ---- filters ----------------------------------------------------------------------------------


def _buses(ctx: _Context, change: dict, where: str) -> list[int]:
    """Buses in the filter: ids, zones (NG, NC, CE, CS, SU) and areas (A01-A13); every given filter must hold.
    No filter: the whole country."""
    size = len(ctx.names)
    picked = set(range(size))
    if change.get("buses"):
        ids = {bus_id(i): i for i in range(size)}
        unknown = sorted(set(change["buses"]) - set(ids))
        if unknown:
            raise GridError("not_found", f"{where}: no existen estas subestaciones: {', '.join(unknown)}")
        picked &= {ids[b] for b in change["buses"]}
    for key, values in (("zones", ctx.zone), ("areas", ctx.area)):
        if change.get(key):
            wanted = {str(z).upper() for z in change[key]}
            unknown = sorted(wanted - set(values))
            if unknown:
                raise GridError(
                    "not_found",
                    f"{where}: {key} desconocidas: {', '.join(unknown)} (válidas: {', '.join(sorted(set(values)))})",
                )
            picked &= {i for i in range(size) if values[i] in wanted}
    return sorted(picked)


def _comuna(ctx: _Context, ref: str, where: str) -> dict:
    comuna = ctx.comunas.get(str(ref).strip()) or ctx.comunas.get(str(ref).strip().lower())
    if comuna is None:
        raise GridError("not_found", f"{where}: comuna desconocida: {ref} (usa el código CUT o el nombre)")
    return comuna


def _comuna_buses(ctx: _Context, change: dict, where: str) -> list[int]:
    out = set()
    for ref in change["comunas"]:
        out |= {
            ctx.node_bus[s["node"]]
            for s in _comuna(ctx, ref, where)["served_by"]
            if s["node"] in ctx.node_bus
        }
    return sorted(out)


def _techs(change: dict, where: str) -> tuple[str, ...]:
    wanted = {t.lower() for t in change.get("tech") or []}
    valid = sorted(set(TECH_ORDER) | set(TAGS))
    unknown = sorted(wanted - set(valid))
    if unknown:
        raise GridError(
            "invalid",
            f"{where}: tecnologías desconocidas: {', '.join(unknown)} (válidas: {', '.join(valid)})",
        )
    techs = {x for t in wanted for x in TAGS.get(t, (t,))}
    return tuple(t for t in TECH_ORDER if t in techs) or TECH_ORDER


def _pick_lines(ctx: _Context, change: dict, where: str) -> list:
    lines = ctx.net.buses.lines
    picked = list(lines)
    if change.get("lines"):
        known = {ln.id for ln in lines}
        unknown = sorted(set(change["lines"]) - known)
        if unknown:
            raise GridError("not_found", f"{where}: no existen estas líneas: {', '.join(unknown)}")
        picked = [ln for ln in picked if ln.id in set(change["lines"])]
    if change.get("kv"):
        picked = [ln for ln in picked if float(ln.kv) in {float(k) for k in change["kv"]}]
    inside = set(_buses(ctx, {k: change.get(k) for k in ("zones", "areas")}, where))
    return [ln for ln in picked if ln.a in inside and ln.b in inside]


def _spread(values: np.ndarray, buses: list[int], change: dict) -> np.ndarray:
    """`factor` scales each bus; `add` is one total for the filter, split by the current value (evenly when all
    are zero)."""
    delta = np.zeros(len(values))
    if not buses:
        return delta
    idx = np.array(buses)
    if change.get("factor") is not None:
        delta[idx] = values[idx] * (change["factor"] - 1.0)
        return delta
    total = float(values[idx].sum())
    delta[idx] = change["add"] * (values[idx] / total if total > 0 else np.full(len(idx), 1.0 / len(idx)))
    return delta


def _floored(values: np.ndarray, delta: np.ndarray) -> np.ndarray:
    """`values + delta`, never below zero on the buses the change lowers; a base value already below zero (net
    injection of embedded generation, 28 buses at feb2025-1500) stays as it was."""
    out = values + delta
    lowered = delta < 0
    out[lowered] = np.maximum(out[lowered], np.minimum(values[lowered], 0.0))
    return out


def _bus_row(
    ctx: _Context,
    i: int | np.integer,
    before: float,
    after: float,
    key: str = "load_mw",
    people: float | None = None,
) -> dict:
    row: dict[str, Any] = {
        "id": bus_id(int(i)),
        "name": ctx.names[i],
        "zone": ctx.zone[i],
        key: [round(float(before), 1), round(float(after), 1)],
    }
    if people is not None:
        row["people"] = round(float(people))
    return row


# ---- outcome ----------------------------------------------------------------------------------


# ---- prepared state ---------------------------------------------------------------------------


def _prepared_totals(p: OperatingPoint) -> dict:
    return {
        "people_total": round(float(p.people.sum())),
        "load_total_mw": round(float(p.load.sum()), 1),
        "gen_total_mw": round(float(p.gen.sum()), 1),
    }


def _overloaded(net, p: OperatingPoint) -> list[dict]:
    """Lines the prepared grid loads over the cascade's limit with no failure: the cascade starts with them as soon
    as a simulation runs."""
    flows = dc_flow(net, set(), p.gen - p.load, find_islands(net, set()))
    limit = CascadeParams().overload_factor
    rows = [
        {"id": ln.id, "kv": ln.kv, "loading_pct": round(100 * abs(f) / ln.capacity_mw, 2)}
        for f, ln in zip(flows, net.lines, strict=True)
        if ln.capacity_mw > 0 and abs(f) / ln.capacity_mw > limit
    ]
    return sorted(rows, key=lambda r: r["id"])


def _should_feed(ctx: _Context, net, p: OperatingPoint) -> dict:
    rows = [
        _source_row(ctx, net, r["bus"], r["people_fed"], r["people_fed"], p, p.gen)
        for r in dependency_workflow(net, p.gen, p.load, p.people)
    ]
    rows.sort(key=lambda r: r["id"])
    return {"sources": rows, "by_zone": _by_zone(rows)}


def _source_row(
    ctx: _Context, net, bus: str, should: int, fed: int, before: OperatingPoint, after_gen
) -> dict:
    """One generating substation. A substation the scenario added (index past the base buses) takes the zone of
    the nearest base one and has no known technology mix."""
    i = int(bus[1:])
    base = i < len(ctx.names)
    near = i if base else _nearest_base_bus(ctx, net, i)
    return {
        "id": bus,
        "name": ctx.names[i] if base else net.names[i],
        "zone": ctx.zone[near],
        "tech": {
            t: round(float(ctx.tech_share[i, k]), 2)
            for k, t in enumerate(TECH_ORDER)
            if base and ctx.tech_share[i, k] >= 0.005
        },
        "gen_mw": [round(float(before.gen[i]), 1), round(float(after_gen[i]), 1)],
        "should_feed": should,
        "feeds": fed,
        "pct_fed": round(100 * fed / should, 2) if should else 100.0,
    }


def _nearest_base_bus(ctx: _Context, net, i: int) -> int:
    base = ctx.net.buses
    return min(range(base.size), key=lambda j: haversine_km(net.lon[i], net.lat[i], base.lon[j], base.lat[j]))


def _by_zone(sources: list[dict]) -> dict[str, dict]:
    """The same stat added up per zone: the resolution the guardrails ask for when reporting damage."""
    out: dict[str, dict] = {}
    for r in sources:
        z = out.setdefault(r["zone"], {"should_feed": 0, "feeds": 0})
        z["should_feed"] += r["should_feed"]
        z["feeds"] += r["feeds"]
    for z in out.values():
        z["pct_fed"] = round(100 * z["feeds"] / z["should_feed"], 2) if z["should_feed"] else 100.0
    return dict(sorted(out.items()))


def _assumptions(ctx: _Context) -> list[dict]:
    node = cascade_params()["stress"]["regulated_share"]
    return [
        {
            "id": "per_capita_demand",
            "text": f"Cada habitante agrega {ctx.per_capita_w:.0f} W: {ctx.regulated_share:.1%} de la demanda del punto "
            "(clientes regulados) dividida por la población. La demanda de clientes libres (minería, industria) no cambia.",
            "source": node.get("source"),
            "is_assumption": True,
        },
        {"id": "tech_split", "text": TECH_NOTE, "is_assumption": True},
        {
            "id": "redispatch",
            "text": BALANCE_RULE + " Sin límite de potencia hacia arriba.",
            "is_assumption": True,
        },
    ]
