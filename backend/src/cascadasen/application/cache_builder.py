"""cascadasen-cache: precompute every single-line cut for each operating point, as static JSON for the web app.

Why: docs/stack.md answers a click from precomputed files, so the demo works without a server.
Layout under the output folder:
  index.json                      points (id, label, year) and the assumptions
  network-<year>.json             reduced network: nodes and lines with ids, coordinates and the map ids behind them
  <point>/buses.json              generation, load and people per bus before the cut
  <point>/baseline.json           the secure base case (no cut)
  <point>/<line id>.json          the cascade for cutting that line
  <point>/<named cut id>.json     the cascade for a named cut (NAMED_CUTS): a whole substation out of service
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cascadasen.domain.cascade.engine import ASSUMPTIONS, run_cascade_workflow
from cascadasen.domain.cascade.network import ReducedNetwork
from cascadasen.domain.cascade.scenario import load_network_and_point


# Named cuts: every line of one substation opens at t = 0. The id is the file name and the "cut" id of the web scenarios.
NAMED_CUTS: dict[str, str] = {
    "falla-charrua-2010": "S/E CHARRUA",  # analogue of 14 Mar 2010 (docs/escenarios.md); ASSUMPTION: a substation fault = all its lines out
}


def lines_of_substation(net: ReducedNetwork, substation: str) -> list[str]:
    """Ids of every line that ends at the substation. Raises if the substation does not exist (a typo must not silently cut nothing)."""
    if substation not in net.index:
        raise ValueError(f"unknown substation: {substation}")
    bus = net.index[substation]
    return sorted(ln.id for ln in net.lines if bus in (ln.a, ln.b))


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
    for cut_id, substation in NAMED_CUTS.items():
        _write(folder / f"{cut_id}.json", run_cascade_workflow(net, op, lines_of_substation(net, substation)))
    return len(net.lines)


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
    args = parser.parse_args()
    counts = build_cache_workflow(args.processed, args.out, args.point)
    print(json.dumps(counts), "->", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
