"""cascadasen-cache: precompute every single-line cut for each operating point, as static JSON for the web app.

Why: docs/stack.md answers a click from precomputed files, so the demo works without a server.
Layout under the output folder:
  index.json                      points (id, label, year) and the assumptions
  network-<year>.json             reduced network: nodes and lines with ids, coordinates and the map ids behind them
  <point>/buses.json              generation, load and people per bus before the cut
  <point>/baseline.json           the secure base case (no cut)
  <point>/<line id>.json          the cascade for cutting that line
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cascadasen.application.theater_world import ProcessedWorld
from cascadasen.domain.cascade.engine import ASSUMPTIONS, run_cascade_workflow
from cascadasen.domain.cascade.network_json import mapa3_network
from cascadasen.infrastructure.files import write_json


def build_cache_workflow(processed: Path, out: Path, point_ids: list[str] | None = None) -> dict:
    world = ProcessedWorld(processed)
    points = _points(world, point_ids)
    out.mkdir(parents=True, exist_ok=True)
    counts = {p["id"]: _build_point(world, out, p) for p in points}
    write_json(out / "index.json", {"points": points, "assumptions": ASSUMPTIONS})
    return counts


def _points(world: ProcessedWorld, wanted: list[str] | None) -> list[dict]:
    return [
        {"id": p["id"], "label": p["label"], "year": int(p["snapshot"][:4]), "snapshot": p["snapshot"]}
        for p in world.records()
        if not wanted or p["id"] in wanted
    ]


def _build_point(world: ProcessedWorld, out: Path, point: dict) -> int:
    theater, op = world.load(point["id"])
    net = theater.buses
    mapa3 = mapa3_network(net, op)
    write_json(out / f"network-{point['year']}.json", {k: mapa3[k] for k in ("nodes", "lines")})
    folder = out / point["id"]
    folder.mkdir(exist_ok=True)
    write_json(folder / "buses.json", mapa3["buses"])
    write_json(folder / "baseline.json", run_cascade_workflow(net, op, []))
    for line in net.lines:
        write_json(folder / f"{line.id}.json", run_cascade_workflow(net, op, [line.id]))
    return len(net.lines)


def main() -> int:
    root = Path(__file__).resolve().parents[4]
    parser = argparse.ArgumentParser(description="Precalcula todos los cortes simples para la app web.")
    parser.add_argument("--processed", type=Path, default=root / "data" / "processed")
    parser.add_argument("--out", type=Path, default=root / "web" / "public" / "cache")
    parser.add_argument("--point", action="append", help="id de un punto de operación (repetible)")
    args = parser.parse_args()
    counts = build_cache_workflow(args.processed, args.out, args.point)
    print(json.dumps(counts), "->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
