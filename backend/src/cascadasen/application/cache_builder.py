"""cascadasen-cache: precompute every single-line cut for each operating point, as static JSON for the web app.

Why: docs/stack.md answers a click from precomputed files, so the demo works without a server.
Layout under the output folder:
  index.json                      points (id, label, year) and the assumptions
  network-<year>.json             reduced network: nodes and lines with ids, coordinates and the map ids behind them
  <point>/buses.json              generation, load and people per bus before the cut
  <point>/baseline.json           the secure base case (no cut)
  <point>/<line id>.json          the cascade for cutting that line
  <point>/dependency.json         per substation: people it feeds (if it generates) and how critical it is (`--only dependency`)
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cascadasen.domain.cascade.engine import ASSUMPTIONS, run_cascade_workflow
from cascadasen.domain.cascade.network import ReducedNetwork
from cascadasen.domain.cascade.criticality import criticality_workflow
from cascadasen.domain.cascade.scenario import load_network_and_point
from cascadasen.domain.cascade.tracing import dependency_workflow


def build_cache_workflow(processed: Path, out: Path, point_ids: list[str] | None = None, only: str = "all") -> dict:
    points = _points(processed, point_ids)
    out.mkdir(parents=True, exist_ok=True)
    if only == "dependency":  # new files only: the cuts and the index are left as they are
        return {p["id"]: _build_dependency(processed, out, p) for p in points}
    counts = {p["id"]: _build_point(processed, out, p) for p in points}
    _write(out / "index.json", {"points": points, "assumptions": ASSUMPTIONS})
    return counts


def _points(processed: Path, wanted: list[str] | None) -> list[dict]:
    ops = json.loads((processed / "operating_points.json").read_text(encoding="utf-8"))["points"]
    return [
        {"id": p["id"], "label": p["label"], "year": int(p["snapshot"][:4]), "snapshot": p["snapshot"]}
        for p in ops
        if not wanted or p["id"] in wanted
    ]


def _build_point(processed: Path, out: Path, point: dict) -> int:
    net, op = load_network_and_point(processed, point["id"])
    _write(out / f"network-{point['year']}.json", _network_json(net))
    folder = out / point["id"]
    folder.mkdir(exist_ok=True)
    _write(
        folder / "buses.json",
        {
            f"B{i:03d}": {
                "gen_mw": round(float(op.gen[i]), 1),
                "load_mw": round(float(op.load[i]), 1),
                "people": round(float(op.people[i])),
            }
            for i in range(net.size)
        },
    )
    _write(folder / "baseline.json", run_cascade_workflow(net, op, []))
    for line in net.lines:
        _write(folder / f"{line.id}.json", run_cascade_workflow(net, op, [line.id]))
    return len(net.lines)


def _build_dependency(processed: Path, out: Path, point: dict) -> int:
    """Who feeds whom (proportional sharing of the base flow) and how much dies without backup if a substation falls."""
    net, op = load_network_and_point(processed, point["id"])
    fed = {row["bus"]: row for row in dependency_workflow(net, op.gen, op.load, op.people)}
    nodes = {}
    for bus, row in criticality_workflow(net, op).items():
        key = f"B{bus:03d}"
        nodes[key] = {**row, "gen_mw": round(float(op.gen[bus]), 1), "people_fed": fed.get(key, {}).get("people_fed", 0), "share_of_people": fed.get(key, {}).get("share_of_people", 0.0)}
    folder = out / point["id"]
    folder.mkdir(exist_ok=True)
    _write(folder / "dependency.json", nodes)
    return len(nodes)


def _network_json(net: ReducedNetwork) -> dict:
    ids = [f"B{i:03d}" for i in range(net.size)]
    return {
        "nodes": [
            {
                "id": ids[i],
                "name": net.names[i],
                "lon": net.lon[i],
                "lat": net.lat[i],
                "kv": net.kv[i],
                "zone": net.zone(i),
                "map_nodes": net.map_nodes[i],
            }
            for i in range(net.size)
        ],
        "lines": [
            {
                "id": ln.id,
                "a": ids[ln.a],
                "b": ids[ln.b],
                "kv": ln.kv,
                "capacity_mw": round(ln.capacity_mw, 1),
                "x_pu": ln.x_pu,
                "map_edges": list(ln.map_edges),
                "branches": list(ln.branches),
            }
            for ln in net.lines
        ],
    }


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(description="Precalcula todos los cortes simples para la app web.")
    parser.add_argument("--processed", type=Path, default=root / "data" / "processed")
    parser.add_argument("--out", type=Path, default=root / "web" / "public" / "cache")
    parser.add_argument("--point", action="append", help="id de un punto de operación (repetible)")
    parser.add_argument("--only", choices=["all", "dependency"], default="all", help="dependency: solo escribe dependency.json por punto")
    args = parser.parse_args()
    counts = build_cache_workflow(args.processed, args.out, args.point, args.only)
    print(json.dumps(counts), "->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
