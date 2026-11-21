"""The theatre's world from `data/processed`: the mapa 3 network per year and its operating points,
built once and cached (docs/mapa3.md section 7)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from cascadasen.domain.cascade.network import reduce_network
from cascadasen.domain.cascade.scenario import OperatingPoint, load_operating_point
from cascadasen.domain.theater.areas import TheaterNetwork, build_theater_network


class ProcessedWorld:
    def __init__(self, processed: Path) -> None:
        self.processed = processed
        ops = json.loads((processed / "operating_points.json").read_text(encoding="utf-8"))["points"]
        self._points = {p["id"]: p for p in ops}
        self._snapshot: dict | None = None
        self._networks: dict[int, TheaterNetwork] = {}
        self._loaded: dict[str, tuple[TheaterNetwork, OperatingPoint]] = {}

    def points(self) -> list[str]:
        return list(self._points)

    def labels(self) -> dict[str, str]:
        return {pid: p["label"] for pid, p in self._points.items()}

    def load(self, point_id: str) -> tuple[TheaterNetwork, OperatingPoint]:
        if point_id not in self._loaded:
            year = int(self._points[point_id]["snapshot"][:4])
            snapshot = self._snapshot_json()
            buses = self._networks[year].buses if year in self._networks else reduce_network(snapshot, year)
            point = load_operating_point(buses, self.processed, point_id, snapshot)
            if year not in self._networks:
                self._networks[year] = build_theater_network(buses, point.people, point.load)
            self._loaded[point_id] = (self._networks[year], point)
        return self._loaded[point_id]

    def _snapshot_json(self) -> dict:
        if self._snapshot is None:
            self._snapshot = json.loads((self.processed / "grid_snapshot.json").read_text(encoding="utf-8"))
        return self._snapshot


@cache
def default_world(processed: str) -> ProcessedWorld:
    return ProcessedWorld(Path(processed))
