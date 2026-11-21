#!/usr/bin/env python3
"""Builds data/processed/baseline_opf.json: a secure base case for each operating point (DC optimal power flow).

Why: the NTSyCS (art. 5-26/5-27) requires operating every series element at or below 100% of its transmission
capacity in Normal state. A merit-order dispatch ignores the network and overloads lines before any cut, so it
cannot be the starting point of an overload cascade. This script redispatches generation at minimum cost so that
no line of the REDUCED network (the one the cascade engine uses) exceeds its capacity, with the same inertia floor.

Needs numpy and scipy (HiGHS). Run after build_operating_points.py:
    python3 data/scripts/build_baseline_opf.py
Keys of gen_by_bus, sync_mw_by_bus and inertia_by_bus_mws are reduced bus names (one per substation).
"""
import collections
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, vstack

SCRIPTS = Path(__file__).resolve().parent
DATA = SCRIPTS.parent
sys.path.insert(0, str(DATA.parent / "backend" / "src"))
from cascadasen.domain.cascade.network import reduce_network  # noqa: E402

BASE_MVA = 100.0
SHED_COST = 5000.0       # USD/MWh, far above any generator: load is shed only if the case is infeasible
CAPACITY_FACTOR = 1.0    # share of a line's capacity allowed pre-contingency (NTSyCS art. 5-27: up to 100%)
NON_SYNCHRONOUS = {"solar PV", "onshore wind", "CSP"}


def build_baseline_workflow() -> dict:
    ops = json.loads((DATA / "processed" / "operating_points.json").read_text(encoding="utf-8"))
    snapshot = json.loads((DATA / "processed" / "grid_snapshot.json").read_text(encoding="utf-8"))
    builder = _load_builder()
    generation = builder._read_generation()
    buses = {b["name"]: b for b in snapshot["model_buses"]}
    nets = {y: reduce_network(snapshot, y) for y in {int(p["snapshot"][:4]) for p in ops["points"]}}
    return {"version": 3, "network": "reduced (one bus per substation), links built after the point's year left out",
            "capacity_factor": CAPACITY_FACTOR,
            "points": [_solve_point(p, nets[int(p["snapshot"][:4])], buses, generation, builder) for p in ops["points"]]}


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_operating_points", SCRIPTS / "build_operating_points.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _solve_point(point: dict, net, buses: dict, generation: dict, builder) -> dict:
    when = point["snapshot"]
    units = [c for g in generation["generators"] if (c := builder._candidate(g, generation, buses, when, when[:4]))]
    for u in units:
        u["rbus"] = net.bus_of_model_bus[u["bus"]]
    lp = _build_lp(point, net, units, _committed(units, builder))
    result = linprog(lp["c"], A_ub=lp["A_ub"], b_ub=lp["b_ub"], A_eq=lp["A_eq"], b_eq=lp["b_eq"], bounds=lp["bounds"], method="highs")
    assert result.status == 0, f"{point['id']}: LP not solved ({result.message})"
    return _summarize(point, result, lp, net, units)


def _committed(units: list, builder) -> set:
    """Same security rule as the merit-order build: cheapest synchronous units stay online until the inertia floor."""
    online, inertia = set(), 0.0
    for i in sorted(range(len(units)), key=lambda i: units[i]["cost"]):
        if inertia >= builder.INERTIA_TARGET_MWS:
            break
        if units[i]["carrier"] not in NON_SYNCHRONOUS and units[i]["inertia"] > 0:
            online.add(i)
            inertia += units[i]["inertia"]
    return online


def _load_by_reduced_bus(point: dict, net) -> np.ndarray:
    load = np.zeros(net.size)
    for bus, mw in point["load_by_bus"].items():
        load[net.bus_of_model_bus[bus]] += mw
    return load


def _build_lp(point: dict, net, units: list, committed: set) -> dict:
    nb, ng, nl = net.size, len(units), len(net.lines)
    g0, t0, s0, n = 0, ng, ng + nb, ng + 2 * nb    # variables: generation, angle per bus, load shed per bus
    load = _load_by_reduced_bus(point, net)
    c = np.zeros(n)
    bounds = []
    room = collections.defaultdict(float)             # what a bus can absorb or export: its own load plus its line capacity
    for ln in net.lines:
        room[ln.a] += ln.capacity_mw
        room[ln.b] += ln.capacity_mw
    for i, u in enumerate(units):
        c[g0 + i] = u["cost"]
        floor = min(u["pmin"], u["avail"], 0.5 * (load[u["rbus"]] + room[u["rbus"]])) if i in committed else 0.0
        bounds.append((floor, u["avail"]))
    bounds += [(-np.pi, np.pi)] * nb + [(0.0, max(float(load[b]), 0.0)) for b in range(nb)]  # some buses have net negative load (PMGD), they cannot be shed
    c[s0:s0 + nb] = SHED_COST
    degree = collections.Counter(x for ln in net.lines for x in (ln.a, ln.b))
    bounds[t0 + max(range(nb), key=lambda b: degree[b])] = (0.0, 0.0)
    rows, cols, vals = [u["rbus"] for u in units] + list(range(nb)), list(range(ng)) + [s0 + b for b in range(nb)], [1.0] * (ng + nb)
    frows, fcols, fvals = [], [], []
    for k, ln in enumerate(net.lines):
        w = BASE_MVA / ln.x_pu
        for bus, sign in ((ln.a, -1.0), (ln.b, 1.0)):       # outgoing flow leaves the bus, incoming flow arrives
            rows += [bus, bus]; cols += [t0 + ln.a, t0 + ln.b]; vals += [sign * w, -sign * w]
        frows += [k, k]; fcols += [t0 + ln.a, t0 + ln.b]; fvals += [w, -w]
    flow = coo_matrix((fvals, (frows, fcols)), shape=(nl, n)).tocsr()
    limit = np.array([CAPACITY_FACTOR * ln.capacity_mw for ln in net.lines])
    return {"c": c, "A_eq": coo_matrix((vals, (rows, cols)), shape=(nb, n)).tocsr(), "b_eq": load, "bounds": bounds,
            "flow": flow, "g0": g0, "s0": s0, "A_ub": vstack([flow, -flow]), "b_ub": np.concatenate([limit, limit])}


def _summarize(point: dict, result, lp: dict, net, units: list) -> dict:
    x = result.x
    gen, sync, inertia = (collections.defaultdict(float) for _ in range(3))
    carrier = collections.defaultdict(float)
    for i, u in enumerate(units):
        mw, name = x[lp["g0"] + i], net.names[u["rbus"]]
        gen[name] += mw
        carrier[u["carrier"]] += mw
        if u["carrier"] not in NON_SYNCHRONOUS and mw > 0.5:
            sync[name] += mw
            inertia[name] += u["inertia"]
    flows = lp["flow"] @ x
    loading = [abs(f) / ln.capacity_mw for f, ln in zip(flows, net.lines)]
    return {"id": point["id"], "total_cost_usd_h": round(result.fun), "shed_mw": round(float(x[lp["s0"]:].sum()), 1),
            "gen_by_bus": {b: round(v, 2) for b, v in gen.items() if v > 0.01},
            "sync_mw_by_bus": {b: round(v, 2) for b, v in sync.items()},
            "inertia_by_bus_mws": {b: round(v) for b, v in inertia.items()},
            "gen_by_carrier_mw": {k: round(v) for k, v in sorted(carrier.items(), key=lambda kv: -kv[1]) if v > 0.5},
            "flow_mw": [round(float(f), 1) for f in flows], "max_loading": round(max(loading), 3),
            "lines_over_90pct": sum(1 for v in loading if v > 0.9), "lines_at_limit": sum(1 for v in loading if v > 0.999)}


if __name__ == "__main__":
    out = build_baseline_workflow()
    path = DATA / "processed" / "baseline_opf.json"
    path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    for p in out["points"]:
        print(f"{p['id']}: cost {p['total_cost_usd_h']:,} USD/h | shed {p['shed_mw']} MW | max loading {p['max_loading']} | >90%: {p['lines_over_90pct']} | at limit: {p['lines_at_limit']}")
