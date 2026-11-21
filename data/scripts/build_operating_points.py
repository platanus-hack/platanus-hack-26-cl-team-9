#!/usr/bin/env python3
"""Builds data/processed/operating_points.json: demand and simulated dispatch per electrical bus, for a few hours.

Why: cutting a line by overload needs to know how much each bus consumes and generates. PyPSA-CL (Ministerio de
Energía, public folder, files git-ignored in data/raw/pypsa_cl/) publishes the model INPUTS: demand (Loads.xlsx),
generators with capacity, marginal cost and inertia (Topology.xlsx), renewable availability (Profiles.xlsx) and
fuel prices (Costs.xlsx). It does not publish the dispatch RESULT, so dispatch is computed here by merit order
with those inputs and a few declared assumptions (see ASSUMPTIONS). Show it as simulated.

Needs openpyxl. Run: python3 data/scripts/build_operating_points.py   (downloads the four files if missing)
"""

import collections
import json
import subprocess
import tempfile
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent
RAW = DATA / "raw" / "pypsa_cl"
LOADS_XLSX = RAW / "Loads.xlsx"
FOLDER = "'/personal/mparedes_minenergia_cl/Documents/PyPSA-CL/1.%20Datos%20de%20entrada%20a%20modelo/"
FILES = ["Loads.xlsx", "Topology.xlsx", "Profiles.xlsx", "Costs.xlsx"]
FUEL_SCENARIO = "Medio"
SHARE_URL = (
    "https://minenergia-my.sharepoint.com/:f:/g/personal/mparedes_minenergia_cl/"
    "IgCWD1vzVNdFSZGLq9yAvae7AWiPl3JViAfaI602hsQZTQ0?e=SH5uDd"
)
FILE_URL = (
    "https://minenergia-my.sharepoint.com/personal/mparedes_minenergia_cl/_api/web/GetFileByServerRelativeUrl("
    "'/personal/mparedes_minenergia_cl/Documents/PyPSA-CL/1.%20Datos%20de%20entrada%20a%20modelo/Loads.xlsx')/$value"
)

# (id, label, scenario, snapshot). PyPSA-CL has one representative day per month, so "2025-02-01" stands for February 2025.
POINTS = [
    (
        "feb2025-1500",
        "Febrero 2025, 15:00 (referencia del 25F)",
        "Media - N2",
        "2025-02-01 15:00",
    ),
    (
        "feb2025-0300",
        "Febrero 2025, 03:00 (demanda mínima)",
        "Media - N2",
        "2025-02-01 03:00",
    ),
    (
        "nov2026-1300",
        "Noviembre 2026, 13:00 (mediodía solar)",
        "Media - N2",
        "2026-11-01 13:00",
    ),
    (
        "nov2026-2000",
        "Noviembre 2026, 20:00 (punta nocturna)",
        "Media - N2",
        "2026-11-01 20:00",
    ),
]
ASSUMPTIONS = [
    "Demanda: perfil modelado de PyPSA-CL (un día representativo por mes, escenario 'Media - N2'). No es la demanda medida de esa hora.",
    "Despacho simulado por orden de mérito con los datos de PyPSA-CL: potencia, costo variable, precio de combustible y disponibilidad solar y eólica de cada generador.",
    "Costo = costo variable + precio del combustible (escenario 'Medio') x consumo específico. Las unidades del consumo específico no están documentadas: el orden entre combustibles es una aproximación.",
    "Hidro de embalse se despacha hasta 60% de su potencia y la hidro de pasada hasta 55% (supuestos: el modelo usa series de agua que no se cargaron).",
    "Seguridad: se mantienen en línea, a su mínimo técnico, las unidades sincrónicas más baratas hasta sumar 31.000 MWs de inercia (piso del rango 31,0 a 42,4 GVAs que cita docs/datasets.md, sin re-verificar). Sin rampas ni tiempos de encendido. Generación = demanda, sin pérdidas.",
    "La demanda de cargas sin barra eléctrica se reparte en proporción entre las barras con demanda.",
    "Cada planta del mapa y cada carga se asigna a la barra del modelo eléctrico más cercana por el grafo del mapa.",
]
RESERVOIR_SHARE, RUN_OF_RIVER_SHARE = 0.60, 0.55
# Security: the operator keeps synchronous units online for inertia. CEN reports 31.0-42.4 GVAs per scenario (docs/datasets.md, not re-checked).
INERTIA_TARGET_MWS = 31000.0
NON_SYNCHRONOUS = {"solar PV", "onshore wind", "CSP"}


def build_operating_points_workflow() -> dict:
    snapshot = json.loads(
        (DATA / "processed" / "grid_snapshot.json").read_text(encoding="utf-8")
    )
    buses = _bus_dictionary(snapshot)
    plant_bus = _plants_to_buses(snapshot, buses)
    demand = _read_demand()
    generation = _read_generation()
    points = [_point(spec, buses, demand, generation) for spec in POINTS]
    return {
        "version": 2,
        "assumptions": ASSUMPTIONS,
        "source": "PyPSA-CL (Ministerio de Energía): Loads, Topology, Profiles, Costs",
        "buses": {
            name: {"node": b["node"], "kv": b["kv"]} for name, b in buses.items()
        },
        "plant_bus": plant_bus,
        "load_bus": demand["load_bus"],
        "points": points,
    }


def _bus_dictionary(snapshot: dict) -> dict:
    return {b["name"]: b for b in snapshot["model_buses"]}


def _plants_to_buses(snapshot: dict, buses: dict) -> dict:
    node_bus = {}
    for b in buses.values():
        if b["node"] and (
            b["node"] not in node_bus or b["kv"] > buses[node_bus[b["node"]]]["kv"]
        ):
            node_bus[b["node"]] = b["name"]
    adjacency = collections.defaultdict(list)
    for e in snapshot["edges"]:
        adjacency[e["source_node"]].append(e["target_node"])
        adjacency[e["target_node"]].append(e["source_node"])
    nearest, queue = dict(node_bus), collections.deque(node_bus)
    while queue:
        node = queue.popleft()
        for other in adjacency[node]:
            if other not in nearest:
                nearest[other] = nearest[node]
                queue.append(other)
    return {
        p["id"]: nearest[p["node"]] for p in snapshot["plants"] if p["node"] in nearest
    }


def _read_demand() -> dict:
    _ensure_loads_file()
    from openpyxl import load_workbook  # imported late: only this step needs it

    wb = load_workbook(LOADS_XLSX, read_only=True, data_only=True)
    rows = wb["loads"].iter_rows(values_only=True)
    columns = list(next(rows)[2:])
    series = {
        (str(r[1]), str(r[0])[:16]): r[2:]
        for r in rows
        if r[0] is not None and str(r[1]) == "Media - N2"
    }
    load_bus = {
        load: node
        for load, node, _ in list(wb["loads-nodes"].iter_rows(values_only=True))[1:]
    }
    return {"columns": columns, "series": series, "load_bus": load_bus}


def _ensure_loads_file() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    jar = Path(tempfile.gettempdir()) / "pypsa_cookies.txt"
    subprocess.run(
        ["curl", "-sL", "-c", str(jar), "-o", "/dev/null", SHARE_URL], check=True
    )
    for name in FILES:
        if not (RAW / name).exists():
            url = FILE_URL.replace("Loads.xlsx", name)
            subprocess.run(
                ["curl", "-sL", "-b", str(jar), "-o", str(RAW / name), url], check=True
            )


def _read_generation() -> dict:
    """Active generators with their bus, cost and availability series for the chosen hours."""
    from openpyxl import load_workbook

    wb = load_workbook(RAW / "Topology.xlsx", read_only=True, data_only=True)
    rows = list(wb["Generators"].iter_rows(values_only=True))
    header = list(rows[0])
    generators = [dict(zip(header, r)) for r in rows[1:] if r[0]]
    profiles = load_workbook(RAW / "Profiles.xlsx", read_only=True, data_only=True)
    profile_of = {
        g: p
        for g, p in list(profiles["profiles-generators"].iter_rows(values_only=True))[
            1:
        ]
    }
    wanted = {spec[3] for spec in POINTS}
    table = profiles["profiles"].iter_rows(values_only=True)
    names = list(next(table)[2:])
    availability = {
        str(r[0])[:16]: dict(zip(names, r[2:]))
        for r in table
        if str(r[0])[:16] in wanted
    }
    costs = load_workbook(RAW / "Costs.xlsx", read_only=True, data_only=True)
    fuel_rows = list(costs["Fuel price"].iter_rows(values_only=True))
    fuel_names = list(fuel_rows[0])
    fuel = {
        (str(r[0])[:4], fuel_names[i]): r[i]
        for r in fuel_rows[1:]
        if r[1] == FUEL_SCENARIO
        for i in range(2, len(fuel_names))
    }
    return {
        "generators": generators,
        "profile_of": profile_of,
        "availability": availability,
        "fuel": fuel,
    }


def _point(spec: tuple, buses: dict, demand: dict, generation: dict) -> dict:
    point_id, label, scenario, when = spec
    load_by_bus, unassigned = _loads(demand, scenario, when, buses)
    total_load = sum(load_by_bus.values()) + unassigned
    scaled = {
        bus: mw * total_load / sum(load_by_bus.values())
        for bus, mw in load_by_bus.items()
    }
    units, unmet = _dispatch(generation, buses, when, total_load)
    gen_by_bus, carrier_mw, inertia = (
        collections.defaultdict(float),
        collections.defaultdict(float),
        collections.defaultdict(float),
    )
    for u in units:
        gen_by_bus[u["bus"]] += u["mw"]
        carrier_mw[u["carrier"]] += u["mw"]
        inertia[u["bus"]] += u["inertia"]
    return {
        "id": point_id,
        "label": label,
        "scenario": scenario,
        "snapshot": when,
        "total_load_mw": round(total_load, 1),
        "unassigned_load_mw": round(unassigned, 1),
        "total_gen_mw": round(sum(gen_by_bus.values()), 1),
        "unmet_mw": round(unmet, 1),
        "gen_by_carrier_mw": {
            c: round(v) for c, v in sorted(carrier_mw.items(), key=lambda x: -x[1])
        },
        "inertia_online_mws": round(sum(inertia.values())),
        "load_by_bus": {b: round(v, 2) for b, v in scaled.items()},
        "gen_by_bus": {b: round(v, 2) for b, v in gen_by_bus.items() if v > 0},
        "inertia_by_bus_mws": {b: round(v) for b, v in inertia.items() if v > 0},
    }


def _loads(demand: dict, scenario: str, when: str, buses: dict) -> tuple[dict, float]:
    values = demand["series"][(scenario, when)]
    by_bus, unassigned = collections.defaultdict(float), 0.0
    for column, mw in zip(demand["columns"], values):
        if not isinstance(mw, (int, float)):
            continue
        bus = demand["load_bus"].get(column)
        if bus in buses:
            by_bus[bus] += mw
        else:
            unassigned += mw
    return dict(by_bus), unassigned


def _dispatch(
    generation: dict, buses: dict, when: str, target: float
) -> tuple[list, float]:
    """Commit enough synchronous units for inertia, then merit order. Returns dispatched units and unmet MW."""
    year = when[:4]
    candidates = [
        c
        for g in generation["generators"]
        if (c := _candidate(g, generation, buses, when, year))
    ]
    candidates.sort(key=lambda c: c["cost"])
    output = _commit_for_inertia(candidates)
    remaining = target - sum(output.values())
    for i, c in enumerate(candidates):
        extra = min(c["avail"] - output.get(i, 0.0), max(remaining, 0.0))
        if extra > 0:
            output[i] = output.get(i, 0.0) + extra
            remaining -= extra
    units = [
        {**candidates[i], "mw": mw, "inertia": candidates[i]["inertia"]}
        for i, mw in output.items()
        if mw > 0
    ]
    return units, max(remaining, 0.0)


def _commit_for_inertia(candidates: list) -> dict:
    output, inertia = {}, 0.0
    for i, c in enumerate(candidates):
        if inertia >= INERTIA_TARGET_MWS:
            break
        if c["carrier"] not in NON_SYNCHRONOUS and c["inertia"] > 0:
            output[i] = min(c["pmin"], c["avail"])
            inertia += c["inertia"]
    return output


def _candidate(
    g: dict, generation: dict, buses: dict, when: str, year: str
) -> dict | None:
    active = str(g["initial_snapshot"])[:16] <= when <= str(g["final_snapshot"])[:16]
    pnom = _num(g["p_nom"])
    if not active or not pnom or g["node"] not in buses:
        return None
    return {
        "bus": g["node"],
        "carrier": g["carrier"],
        "pnom": pnom,
        "pmin": pnom * (_num(g["p_min_pu"]) or 0.0),
        "avail": pnom * _availability(g, generation, when),
        "cost": _cost(g, generation, year),
        "inertia": _num(g["inertia_contribution"]) or 0.0,
    }


def _availability(g: dict, generation: dict, when: str) -> float:
    profile = generation["profile_of"].get(g["name"])
    if profile:
        return min(
            1.0, max(0.0, _num(generation["availability"][when].get(profile)) or 0.0)
        )
    return {"hydro reservoir": RESERVOIR_SHARE, "hydro ROR": RUN_OF_RIVER_SHARE}.get(
        g["carrier"], _num(g["p_max_pu"]) or 1.0
    )


def _cost(g: dict, generation: dict, year: str) -> float:
    price = _num(generation["fuel"].get((year, g["fuel/water node"]))) or 0.0
    return (_num(g["marginal_cost"]) or 0.0) + price * (
        _num(g["heat_rate/efficiency"]) or 0.0
    )


def _num(value) -> float | None:
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _self_check(result: dict) -> None:
    for p in result["points"]:
        assert p["unmet_mw"] < 1, f"{p['id']}: not enough generation"
        assert abs(p["total_gen_mw"] - p["total_load_mw"]) < 5, (
            f"{p['id']}: generation and load differ"
        )
        assert abs(sum(p["load_by_bus"].values()) - p["total_load_mw"]) < 5
        assert p["inertia_online_mws"] > 0
    assert len(result["load_bus"]) == 259


if __name__ == "__main__":
    out = build_operating_points_workflow()
    _self_check(out)
    path = DATA / "processed" / "operating_points.json"
    path.write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(
        f"{len(out['points'])} points, {len(out['plant_bus'])} plants and {len(out['load_bus'])} loads mapped -> {path} ({path.stat().st_size / 1e3:.0f} KB)"
    )
    for p in out["points"]:
        print(
            f"  {p['id']}: load {p['total_load_mw']} MW, gen {p['total_gen_mw']} MW, inertia {p['inertia_online_mws']:,} MWs | {p['gen_by_carrier_mw']}"
        )
