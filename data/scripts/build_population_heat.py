"""Where people are served, as weighted points for a heat map: [lon, lat, people] per delivery substation.

Source: data/processed/node_index.json (`served_population` per substation, from the INE census assigned to the nearest
delivery substation, see `grid_snapshot.json` assumptions). Output: data/processed/geo/population.json.

Run: python data/scripts/build_population_heat.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "processed" / "node_index.json"
OUT = ROOT / "data" / "processed" / "geo" / "population.json"


def population_points(node_index: dict) -> list[list[float]]:
    """One point per substation that serves people, heaviest first. Coordinates are rounded to 4 decimals (about 10 m)."""
    rows = [
        [round(n["lon"], 4), round(n["lat"], 4), round(n["served_population"])]
        for n in node_index.values()
        if n.get("served_population") and n.get("lon") is not None and n.get("lat") is not None
    ]
    return sorted(rows, key=lambda r: -r[2])


def main() -> int:
    points = population_points(json.loads(SOURCE.read_text(encoding="utf-8")))
    OUT.write_text(json.dumps(points, separators=(",", ":")), encoding="utf-8")
    print(f"{len(points)} substations, {sum(p[2] for p in points):,} people -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
