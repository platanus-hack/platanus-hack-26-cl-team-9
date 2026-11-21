#!/usr/bin/env python3
"""Builds data/processed/baseline_opf.json: a secure base case for each operating point (DC optimal power flow).

Why: the NTSyCS (art. 5-26/5-27) requires operating every series element at or below 100% of its transmission
capacity in Normal state, and the N-1 criterion. A merit-order dispatch ignores the network and overloads lines
before any cut, so it cannot be the starting point of an overload cascade. This script redispatches generation
at minimum cost so that no branch exceeds its capacity (s_nom) and demand is served, with the same inertia floor.

Needs numpy and scipy (HiGHS). Run after build_operating_points.py:
    python3 data/scripts/build_baseline_opf.py
"""
import collections
import importlib.util
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

SCRIPTS = Path(__file__).resolve().parent
DATA = SCRIPTS.parent
BASE_MVA = 100.0
SHED_COST = 5000.0       # USD/MWh, far above any generator: load is shed only if the case is infeasible
CAPACITY_FACTOR = 1.0    # share of s_nom allowed pre-contingency (NTSyCS art. 5-27: up to 100% of the transmission capacity)


def build_baseline_workflow() -> dict:
    ops = json.loads((DATA / "processed" / "operating_points.json").read_text(encoding="utf-8"))
    snapshot = json.loads((DATA / "processed" / "grid_snapshot.json").read_text(encoding="utf-8"))
    builder = _load_builder()
    generation = builder._read_generation()
    buses = {b["name"]: b for b in snapshot["model_buses"]}
    return {"version": 1, "capacity_factor": CAPACITY_FACTOR, "branches": [_branch_row(r) for r in snapshot["model_branches"]],
            "points": [_solve_point(p, snapshot, buses, generation, builder) for p in ops["points"]]}


def _load_builder():
    spec = importlib.util.spec_from_file_location("build_operating_points", SCRIPTS / "build_operating_points.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _branch_row(r: dict) -> list:
    return [r["name"], r["bus0"], r["bus1"], r["s_nom_mva"], r["x_pu"]]


def _solve_point(point: dict, snapshot: dict, buses: dict, generation: dict, builder) -> dict:
    names = list(buses)
    index = {n: i for i, n in enumerate(names)}
    branches = snapshot["model_branches"]
    year, when = point["snapshot"][:4], point["snapshot"]
    units = [c for g in generation["generators"] if (c := builder._candidate(g, generation, buses, when, year))]
    committed = _committed(units, builder)
    lp = _build_lp(point, names, index, branches, units, committed)
    result = linprog(lp["c"], A_ub=lp["A_ub"], b_ub=lp["b_ub"], A_eq=lp["A_eq"], b_eq=lp["b_eq"], bounds=lp["bounds"], method="highs")
    assert result.status == 0, f"{point['id']}: LP not solved ({result.message})"
    return _summarize(point, result, lp, names, branches, units)


def _committed(units: list, builder) -> set:
    """Same security rule as the merit-order build: cheapest synchronous units stay online until the inertia floor."""
    order = sorted(range(len(units)), key=lambda i: units[i]["cost"])
    online, inertia = set(), 0.0
    for i in order:
        if inertia >= builder.INERTIA_TARGET_MWS:
            break
        if units[i]["carrier"] not in builder.NON_SYNCHRONOUS and units[i]["inertia"] > 0:
            online.add(i)
            inertia += units[i]["inertia"]
    return online


def _build_lp(point, names, index, branches, units, committed) -> dict:
    nb, ng, nl = len(names), len(units), len(branches)
    # variable order: generation (ng), voltage angle per bus (nb), load shed per bus (nb)
    g0, t0, s0 = 0, ng, ng + nb
    n = ng + 2 * nb
    c = np.zeros(n)
    bounds = []
    for i, u in enumerate(units):
        c[g0 + i] = u["cost"]
        low = min(u["pmin"], u["avail"]) if i in committed else 0.0
        bounds.append((low, u["avail"]))
    bounds += [(-np.pi, np.pi)] * nb
    load = {b: point["load_by_bus"].get(b, 0.0) for b in names}
    bounds += [(0.0, max(load[b], 0.0)) for b in names]
    c[s0:s0 + nb] = SHED_COST
    slack = max(range(nb), key=lambda i: sum(1 for r in branches if names[i] in (r["bus0"], r["bus1"])))
    bounds[t0 + slack] = (0.0, 0.0)
    rows, cols, vals = [], [], []
    for i, u in enumerate(units):                                  # + generation at its bus
        rows.append(index[u["bus"]]); cols.append(g0 + i); vals.append(1.0)
    for b in range(nb):                                            # + load shed
        rows.append(b); cols.append(s0 + b); vals.append(1.0)
    flow_rows, flow_cols, flow_vals = [], [], []
    for l, r in enumerate(branches):
        i, j, w = index[r["bus0"]], index[r["bus1"]], BASE_MVA / r["x_pu"]
        for bus, other, sign in ((i, j, -1.0), (j, i, 1.0)):       # - outgoing flow, + incoming flow in the balance
            rows += [bus, bus]; cols += [t0 + i, t0 + j]; vals += [sign * w, -sign * w]
        flow_rows += [l, l]; flow_cols += [t0 + i, t0 + j]; flow_vals += [w, -w]
    A_eq = coo_matrix((vals, (rows, cols)), shape=(nb, n)).tocsr()
    b_eq = np.array([load[b] for b in names])
    flow = coo_matrix((flow_vals, (flow_rows, flow_cols)), shape=(nl, n)).tocsr()
    limit = np.array([CAPACITY_FACTOR * r["s_nom_mva"] for r in branches])
    from scipy.sparse import vstack
    return {"c": c, "A_eq": A_eq, "b_eq": b_eq, "bounds": bounds, "flow": flow, "g0": g0, "t0": t0, "s0": s0,
            "A_ub": vstack([flow, -flow]), "b_ub": np.concatenate([limit, limit])}


def _summarize(point, result, lp, names, branches, units) -> dict:
    x = result.x
    gen_by_bus, carrier = collections.defaultdict(float), collections.defaultdict(float)
    for i, u in enumerate(units):
        gen_by_bus[u["bus"]] += x[lp["g0"] + i]
        carrier[u["carrier"]] += x[lp["g0"] + i]
    flows = lp["flow"] @ x
    loading = [abs(f) / r["s_nom_mva"] for f, r in zip(flows, branches)]
    return {"id": point["id"], "total_cost_usd_h": round(result.fun), "shed_mw": round(float(x[lp["s0"]:].sum()), 1),
            "gen_by_bus": {b: round(v, 2) for b, v in gen_by_bus.items() if v > 0.01},
            "gen_by_carrier_mw": {k: round(v) for k, v in sorted(carrier.items(), key=lambda kv: -kv[1]) if v > 0.5},
            "flow_mw": [round(float(f), 1) for f in flows], "max_loading": round(max(loading), 3),
            "branches_over_90pct": sum(1 for v in loading if v > 0.9), "branches_at_limit": sum(1 for v in loading if v > 0.999)}


if __name__ == "__main__":
    out = build_baseline_workflow()
    path = DATA / "processed" / "baseline_opf.json"
    path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    names = {r[0]: i for i, r in enumerate(out["branches"])}
    corridor = names.get("S/E NUEVA PAN DE AZUCAR_500->S/E NUEVA MAITENCILLO_500")
    for p in out["points"]:
        print(f"{p['id']}: cost {p['total_cost_usd_h']:,} USD/h | shed {p['shed_mw']} MW | max loading {p['max_loading']} | >90%: {p['branches_over_90pct']} | at limit: {p['branches_at_limit']} | 25F corridor {p['flow_mw'][corridor]} MW | {p['gen_by_carrier_mw']}")
