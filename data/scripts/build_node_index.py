#!/usr/bin/env python3
"""Builds data/processed/node_index.json: one record per substation or tap with everything the map popup shows.

Why: the map must answer "what is this node?" without calling the backend, so the web app reads one
static file keyed by node id (ficha, lines, plants, storage, served comunas, electrical model).
Reads only files already in data/processed/. Run from anywhere: python3 data/scripts/build_node_index.py
"""

import json
import re
from collections import defaultdict
from pathlib import Path

PROCESSED = Path(__file__).resolve().parent.parent / "processed"
TOP_PLANTS = 8


def build_node_index_workflow() -> dict:
    nodes = _node_records()
    snapshot = _load("grid_snapshot.json")
    network = _load("sen_network.json")
    _add_cen_ids(nodes, snapshot)
    _add_lines(nodes, network)
    _add_generation(nodes, snapshot)
    _add_storage(nodes, snapshot)
    _add_population(nodes, snapshot)
    _add_electrical_model(nodes, snapshot)
    _add_operating_points(nodes)
    return nodes


def _load(name: str):
    return json.loads((PROCESSED / name).read_text(encoding="utf-8"))


def _node_records() -> dict:
    nodes = {}
    for layer in ("substations", "taps"):
        for feature in _load(f"geo/{layer}.geojson")["features"]:
            p = feature["properties"]
            nodes[p["id"]] = {
                "id": p["id"],
                "name": p["name"],
                "kind": p["kind"],
                "kv": p["kv"],
                "kv_levels": p["kv_levels"],
                "owner": p["owner"],
                "system": p["system"],
                "segment": p["segment"],
                "macro_zone": p["macro_zone"],
                "region_code": p["region_code"],
                "comuna_code": p["comuna_code"],
                "lon": p["lon"],
                "lat": p["lat"],
                "in_main_grid": p["in_main_grid"],
                "degree": p["degree"],
                "delivers": p["delivers"],
                "generation_mw": p["generation_mw"],
                "served_population": p["served_population"],
                "lines": [],
                "plants": [],
                "storage": [],
                "storage_candidates": [0, 0.0],
                "comunas": [],
                "model_buses": [],
                "model_branches": [],
            }
    return nodes


def _add_cen_ids(nodes: dict, snapshot: dict) -> None:
    for n in snapshot["nodes"]:
        if n["id"] in nodes:
            ids = n.get("ids") or {}
            nodes[n["id"]]["cen"] = {
                "id": ids.get("cen_id"),
                "code": ids.get("cen_code"),
                "scada": ids.get("flag_scada"),
                "comm": ids.get("flag_equipocom"),
            }


def _add_lines(nodes: dict, network: dict) -> None:
    names = {n["id"]: n["name"] for n in network["nodes"]}
    for e in network["edges"]:
        for here, other in ((e["source"], e["target"]), (e["target"], e["source"])):
            if here in nodes:
                nodes[here]["lines"].append(
                    [
                        e["id"],
                        e["kv"],
                        e["circuit"],
                        names.get(other, other),
                        other,
                        e["length_km"],
                        e["s_nom_mva"],
                        e["x_ohm"],
                        e["topology_source"],
                        bool(e["is_assumption"]),
                        e["kind"],
                    ]
                )
    for n in nodes.values():
        n["lines"].sort(key=lambda r: -(r[1] or 0))


def _add_generation(nodes: dict, snapshot: dict) -> None:
    for p in snapshot["plants"]:
        if p["node"] in nodes and p["mw"]:
            nodes[p["node"]]["plants"].append([p["name"], p["tech"], p["mw"]])
    for n in nodes.values():
        n["plants"].sort(key=lambda r: -r[2])
        n["plants_count"] = len(n["plants"])
        n["plants"] = n["plants"][:TOP_PLANTS]


CANDIDATE_NAME = re.compile(r"^[A-Za-z]+_\S+_\d+h$")


def _add_storage(nodes: dict, snapshot: dict) -> None:
    # PyPSA-CL storage named "<TYPE>_<node>_<h>h" (BESS or CAES, 2,000-5,000 MW each, 699 GW in the whole file)
    # looks like expansion candidates, not existing batteries: keep it apart as a count and a MW total.
    for s in snapshot["storage"]:
        if s["node"] not in nodes:
            continue
        if s["source"] == "pypsa_cl" and CANDIDATE_NAME.match(s["name"]):
            c = nodes[s["node"]]["storage_candidates"]
            c[0] += 1
            c[1] += s["mw"] or 0
        else:
            nodes[s["node"]]["storage"].append(
                [s["name"], s["mw"], s["hours"], s["equipment"], s["source"]]
            )


def _add_population(nodes: dict, snapshot: dict) -> None:
    for c in snapshot["comunas"]:
        for s in c["served_by"]:
            if s["node"] in nodes:
                nodes[s["node"]]["comunas"].append(
                    [c["name"], round(s["population"]), s["share"]]
                )


def _add_electrical_model(nodes: dict, snapshot: dict) -> None:
    for b in snapshot["model_buses"]:
        if b["node"] in nodes:
            nodes[b["node"]]["model_buses"].append([b["name"], b["kv"]])
    for r in snapshot["model_branches"]:
        for node in {r["node0"], r["node1"]}:
            if node in nodes:
                nodes[node]["model_branches"].append(
                    [r["name"], r["asset_type"], r["s_nom_mva"], r["x_pu"], r["r_pu"]]
                )


def _add_operating_points(nodes: dict) -> None:
    """Demand and simulated dispatch per node and per hour, summed over the node's electrical buses (see build_operating_points.py)."""
    path = PROCESSED / "operating_points.json"
    if not path.exists():
        return
    ops = json.loads(path.read_text(encoding="utf-8"))
    bus_node = {name: b["node"] for name, b in ops["buses"].items()}
    for point in ops["points"]:
        totals = defaultdict(lambda: [0.0, 0.0])
        for bus, mw in point["load_by_bus"].items():
            totals[bus_node[bus]][0] += mw
        for bus, mw in point["gen_by_bus"].items():
            totals[bus_node[bus]][1] += mw
        for node_id, (load, gen) in totals.items():
            if node_id in nodes:
                nodes[node_id].setdefault("operating", {})[point["id"]] = [
                    round(load, 1),
                    round(gen, 1),
                ]
    for n in nodes.values():
        n.setdefault("operating", {})


def _self_check(nodes: dict) -> None:
    hub = nodes["SE560"]  # S/E Alto Jahuel 500 kV, inspected by hand
    assert hub["name"] == "S/E ALTO JAHUEL" and len(hub["lines"]) == 20
    assert hub["plants_count"] == 10 and hub["storage_candidates"][0] > 0
    assert sum(len(n["lines"]) for n in nodes.values()) > 3000


if __name__ == "__main__":
    index = build_node_index_workflow()
    _self_check(index)
    out = PROCESSED / "node_index.json"
    out.write_text(
        json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"{len(index)} nodes -> {out} ({out.stat().st_size / 1e6:.2f} MB)")
