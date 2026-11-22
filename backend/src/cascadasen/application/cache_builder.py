"""cascadasen-cache: precompute every single-line cut and every substation shutdown for each operating point, as static JSON for the web app.

Why: docs/stack.md answers a click from precomputed files, so the demo works without a server.
Layout under the output folder:
  index.json                      points (id, label, year) and the assumptions
  network-<year>.json             reduced network: nodes and lines with ids, coordinates and the map ids behind them
  <point>/buses.json              generation, load and people per bus before the cut
  <point>/baseline.json           the secure base case (no cut)
  <point>/<line id>.json          the cascade for cutting that line
  <point>/sub-<bus id>.json       the cascade for shutting down that substation: every line of the bus opens at t = 0
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cascadasen.domain.cascade.engine import ASSUMPTIONS, run_cascade_workflow
from cascadasen.domain.cascade.network import ReducedNetwork
from cascadasen.domain.cascade.scenario import load_network_and_point


def build_cache_workflow(processed: Path, out: Path, point_ids: list[str] | None = None) -> dict:
    points = _points(processed, point_ids)
    out.mkdir(parents=True, exist_ok=True)
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


def _build_point(processed: Path, out: Path, point: dict) -> dict:
    net, op = load_network_and_point(processed, point["id"])
    _write(out / f"network-{point['year']}.json", network_json(net))
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
    substations = 0
    for i in range(net.size):
        ids = [ln.id for ln in net.lines if i in (ln.a, ln.b)]
        if ids:
            _write(folder / f"sub-B{i:03d}.json", run_cascade_workflow(net, op, ids))
            substations += 1
    return {"lines": len(net.lines), "substations": substations}


def network_json(net: ReducedNetwork) -> dict:
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
                "country": net.country,
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
                "country": ln.country,
            }
            for ln in net.lines
        ],
    }


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def main() -> int:
    root = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(
        description="Precalcula los cortes de una línea y el apagado de cada subestación para la app web."
    )
    parser.add_argument("--processed", type=Path, default=root / "data" / "processed")
    parser.add_argument("--out", type=Path, default=root / "web" / "public" / "cache")
    parser.add_argument("--point", action="append", help="id de un punto de operación (repetible)")
    args = parser.parse_args()
    counts = build_cache_workflow(args.processed, args.out, args.point)
    print(json.dumps(counts), "->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
