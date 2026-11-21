#!/usr/bin/env python3
"""Builds data/processed/operating_points.json: demand and simulated dispatch per electrical bus, for a few hours.

Why: cutting a line by overload needs to know how much each bus consumes and generates. Demand comes from
PyPSA-CL (Ministerio de Energía, data/raw/pypsa_cl/Loads.xlsx, 139 MB, git-ignored). Dispatch is NOT published
there, so it is simulated here with explicit assumptions (see ASSUMPTIONS) and must be shown as such.

Needs openpyxl. Run: python3 data/scripts/build_operating_points.py   (downloads Loads.xlsx if missing)
"""
import collections
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent
LOADS_XLSX = DATA / "raw" / "pypsa_cl" / "Loads.xlsx"
SHARE_URL = ("https://minenergia-my.sharepoint.com/:f:/g/personal/mparedes_minenergia_cl/"
             "IgCWD1vzVNdFSZGLq9yAvae7AWiPl3JViAfaI602hsQZTQ0?e=SH5uDd")
FILE_URL = ("https://minenergia-my.sharepoint.com/personal/mparedes_minenergia_cl/_api/web/GetFileByServerRelativeUrl("
            "'/personal/mparedes_minenergia_cl/Documents/PyPSA-CL/1.%20Datos%20de%20entrada%20a%20modelo/Loads.xlsx')/$value")

# (id, label, scenario, snapshot). PyPSA-CL has one representative day per month, so "2025-02-01" stands for February 2025.
POINTS = [
    ("feb2025-1500", "Febrero 2025, 15:00 (referencia del 25F)", "Media - N2", "2025-02-01 15:00"),
    ("feb2025-0300", "Febrero 2025, 03:00 (demanda mínima)", "Media - N2", "2025-02-01 03:00"),
    ("nov2026-1300", "Noviembre 2026, 13:00 (mediodía solar)", "Media - N2", "2026-11-01 13:00"),
    ("nov2026-2000", "Noviembre 2026, 20:00 (punta nocturna)", "Media - N2", "2026-11-01 20:00"),
]
ASSUMPTIONS = [
    "Demanda: perfil modelado de PyPSA-CL (un día representativo por mes, escenario 'Media - N2'). No es la demanda medida de esa hora.",
    "Despacho simulado: primero solar, eólica, geotermia y bioenergía según un factor de planta supuesto; luego hidro (hasta 60% de su potencia instalada) y por último térmica.",
    "Factores de planta supuestos: solar con forma de campana (máx. 0,80 al mediodía), eólica 0,35 ± 0,10, geotermia 0,85, bioenergía 0,55.",
    "Generación = demanda total (sin pérdidas). La demanda de cargas sin barra eléctrica se reparte en proporción entre las barras con demanda.",
    "Cada planta y cada carga se asigna a la barra del modelo eléctrico más cercana por el grafo del mapa.",
]
SOLAR_PEAK, WIND_MEAN, WIND_SWING, GEOTHERMAL, BIOENERGY, HYDRO_SHARE = 0.80, 0.35, 0.10, 0.85, 0.55, 0.6


def build_operating_points_workflow() -> dict:
    snapshot = json.loads((DATA / "processed" / "grid_snapshot.json").read_text(encoding="utf-8"))
    buses = _bus_dictionary(snapshot)
    plant_bus = _plants_to_buses(snapshot, buses)
    demand = _read_demand()
    points = [_point(spec, snapshot, buses, plant_bus, demand) for spec in POINTS]
    return {"version": 1, "assumptions": ASSUMPTIONS, "source_demand": "PyPSA-CL Loads.xlsx (Ministerio de Energía)",
            "buses": {name: {"node": b["node"], "kv": b["kv"]} for name, b in buses.items()},
            "plant_bus": plant_bus, "load_bus": demand["load_bus"], "points": points}


def _bus_dictionary(snapshot: dict) -> dict:
    return {b["name"]: b for b in snapshot["model_buses"]}


def _plants_to_buses(snapshot: dict, buses: dict) -> dict:
    node_bus = {}
    for b in buses.values():
        if b["node"] and (b["node"] not in node_bus or b["kv"] > buses[node_bus[b["node"]]]["kv"]):
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
    return {p["id"]: nearest[p["node"]] for p in snapshot["plants"] if p["node"] in nearest}


def _read_demand() -> dict:
    _ensure_loads_file()
    from openpyxl import load_workbook  # imported late: only this step needs it
    wb = load_workbook(LOADS_XLSX, read_only=True, data_only=True)
    rows = wb["loads"].iter_rows(values_only=True)
    columns = list(next(rows)[2:])
    series = {(str(r[1]), str(r[0])[:16]): r[2:] for r in rows if r[0] is not None and str(r[1]) == "Media - N2"}
    load_bus = {load: node for load, node, _ in list(wb["loads-nodes"].iter_rows(values_only=True))[1:]}
    return {"columns": columns, "series": series, "load_bus": load_bus}


def _ensure_loads_file() -> None:
    if LOADS_XLSX.exists():
        return
    LOADS_XLSX.parent.mkdir(parents=True, exist_ok=True)
    jar = Path(tempfile.gettempdir()) / "pypsa_cookies.txt"
    subprocess.run(["curl", "-sL", "-c", str(jar), "-o", "/dev/null", SHARE_URL], check=True)
    subprocess.run(["curl", "-sL", "-b", str(jar), "-o", str(LOADS_XLSX), FILE_URL], check=True)


def _point(spec: tuple, snapshot: dict, buses: dict, plant_bus: dict, demand: dict) -> dict:
    point_id, label, scenario, when = spec
    load_by_bus, unassigned = _loads(demand, scenario, when, buses)
    total_load = sum(load_by_bus.values()) + unassigned
    scaled = {bus: mw * total_load / sum(load_by_bus.values()) for bus, mw in load_by_bus.items()}
    gen_by_bus, unmet = _dispatch(snapshot, plant_bus, int(when[11:13]), total_load)
    return {"id": point_id, "label": label, "scenario": scenario, "snapshot": when,
            "total_load_mw": round(total_load, 1), "unassigned_load_mw": round(unassigned, 1),
            "total_gen_mw": round(sum(gen_by_bus.values()), 1), "unmet_mw": round(unmet, 1),
            "load_by_bus": {b: round(v, 2) for b, v in scaled.items()},
            "gen_by_bus": {b: round(v, 2) for b, v in gen_by_bus.items() if v > 0}}


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


def _capacity_factor(tech: str, hour: int) -> float | None:
    if tech == "solar":
        return SOLAR_PEAK * math.sin(math.pi * (hour - 6.5) / 12) if 6.5 < hour < 18.5 else 0.0
    return {"eolica": WIND_MEAN + WIND_SWING * math.cos((hour - 3) / 24 * 2 * math.pi),
            "geotermica": GEOTHERMAL, "bioenergia": BIOENERGY}.get(tech)


def _dispatch(snapshot: dict, plant_bus: dict, hour: int, target: float) -> tuple[dict, float]:
    gen, remaining = collections.defaultdict(float), target
    plants = [p for p in snapshot["plants"] if p["mw"] and p["id"] in plant_bus]
    must_run = [(plant_bus[p["id"]], p["mw"] * _capacity_factor(p["tech"], hour)) for p in plants if _capacity_factor(p["tech"], hour) is not None]
    remaining = _fill(gen, must_run, remaining)
    hydro = [(plant_bus[p["id"]], p["mw"] * HYDRO_SHARE) for p in plants if p["tech"] == "hidro"]
    remaining = _fill(gen, hydro, remaining)
    thermal = [(plant_bus[p["id"]], p["mw"]) for p in plants if p["tech"] not in ("hidro",) and _capacity_factor(p["tech"], hour) is None]
    return gen, _fill(gen, thermal, remaining)


def _fill(gen: dict, group: list, remaining: float) -> float:
    available = sum(mw for _, mw in group)
    if remaining <= 0 or available <= 0:
        return remaining
    share = min(1.0, remaining / available)
    for bus, mw in group:
        gen[bus] += mw * share
    return remaining - available * share


def _self_check(result: dict) -> None:
    for p in result["points"]:
        assert p["unmet_mw"] < 1, f"{p['id']}: not enough generation"
        assert abs(p["total_gen_mw"] - p["total_load_mw"]) < 5, f"{p['id']}: generation and load differ"
        assert abs(sum(p["load_by_bus"].values()) - p["total_load_mw"]) < 5
    assert len(result["load_bus"]) == 259


if __name__ == "__main__":
    out = build_operating_points_workflow()
    _self_check(out)
    path = DATA / "processed" / "operating_points.json"
    path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(out['points'])} points, {len(out['plant_bus'])} plants and {len(out['load_bus'])} loads mapped -> {path} ({path.stat().st_size / 1e3:.0f} KB)")
    for p in out["points"]:
        print(f"  {p['id']}: load {p['total_load_mw']} MW, gen {p['total_gen_mw']} MW, unassigned load {p['unassigned_load_mw']} MW")
