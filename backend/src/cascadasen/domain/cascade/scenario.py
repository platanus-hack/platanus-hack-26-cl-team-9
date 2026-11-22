"""Operating point on the reduced network: generation, load, inertia and people per bus."""

from __future__ import annotations

import collections
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .network import ReducedNetwork, reduce_network


@dataclass
class OperatingPoint:
    id: str
    label: str
    load: np.ndarray
    gen: np.ndarray
    sync_mw: np.ndarray
    inertia_mws: np.ndarray
    people: np.ndarray

    @property
    def nonsync_mw(self) -> np.ndarray:
        return np.maximum(self.gen - self.sync_mw, 0.0)


def load_network_and_point(processed: Path, point_id: str) -> tuple[ReducedNetwork, OperatingPoint]:
    """The network of the point's year (links built later are left out) together with its operating point."""
    snapshot = _read(processed / "grid_snapshot.json")
    when = next(p for p in _read(processed / "operating_points.json")["points"] if p["id"] == point_id)[
        "snapshot"
    ]
    net = reduce_network(snapshot, int(when[:4]))
    return net, load_operating_point(net, processed, point_id, snapshot)


def load_operating_point(
    net: ReducedNetwork, processed: Path, point_id: str, snapshot: dict | None = None
) -> OperatingPoint:
    return operating_point_from_docs(
        net,
        _read(processed / "operating_points.json"),
        _read(processed / "baseline_opf.json"),
        snapshot or _read(processed / "grid_snapshot.json"),
        point_id,
    )


def operating_point_from_docs(
    net: ReducedNetwork, ops: dict, base: dict, snapshot: dict, point_id: str
) -> OperatingPoint:
    """The same point from documents already in memory (the grid store hands over documents, not paths)."""
    demand = next(p for p in ops["points"] if p["id"] == point_id)
    secure = next(p for p in base["points"] if p["id"] == point_id)
    return OperatingPoint(
        id=point_id,
        label=demand["label"],
        load=_by_bus(net, demand["load_by_bus"]),
        gen=_by_reduced(net, secure["gen_by_bus"]),
        sync_mw=_by_reduced(net, secure["sync_mw_by_bus"]),
        inertia_mws=_by_reduced(net, secure["inertia_by_bus_mws"]),
        people=_people(net, snapshot),
    )


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _by_bus(net: ReducedNetwork, values: dict[str, float]) -> np.ndarray:
    out = np.zeros(net.size)
    for model_bus, v in values.items():
        out[net.bus_of_model_bus[model_bus]] += v
    return out


def _by_reduced(net: ReducedNetwork, values: dict[str, float]) -> np.ndarray:
    out = np.zeros(net.size)
    for name, v in values.items():
        out[net.index[name]] += v
    return out


def _people(net: ReducedNetwork, snapshot: dict) -> np.ndarray:
    """People served per reduced bus: each comuna's population goes to the bus nearest to the node that serves it."""
    node_bus = _nearest_bus_per_node(net, snapshot)
    out = np.zeros(net.size)
    for comuna in snapshot["comunas"]:
        for s in comuna["served_by"]:
            if s["node"] in node_bus:
                out[node_bus[s["node"]]] += s["population"]
    return out


def people_by_comuna(net: ReducedNetwork, snapshot: dict) -> list[dict[str, float]]:
    """The same assignment as _people, kept per comuna: entry i maps a comuna cut code to the people bus i serves there."""
    node_bus = _nearest_bus_per_node(net, snapshot)
    out: list[dict[str, float]] = [{} for _ in range(net.size)]
    for comuna in snapshot["comunas"]:
        for s in comuna["served_by"]:
            if s["node"] in node_bus:
                rows = out[node_bus[s["node"]]]
                rows[comuna["cut"]] = rows.get(comuna["cut"], 0.0) + s["population"]
    return out


def _nearest_bus_per_node(net: ReducedNetwork, snapshot: dict) -> dict[str, int]:
    nearest: dict[str, int] = {}
    for b in sorted(snapshot["model_buses"], key=lambda b: b["kv"]):
        if b["node"]:
            nearest[b["node"]] = net.bus_of_model_bus[
                b["name"]
            ]  # highest kV wins: sorted ascending, last write kept
    adjacency = collections.defaultdict(list)
    for e in snapshot["edges"]:
        adjacency[e["source_node"]].append(e["target_node"])
        adjacency[e["target_node"]].append(e["source_node"])
    queue = collections.deque(nearest)
    while queue:
        node = queue.popleft()
        for other in adjacency[node]:
            if other not in nearest:
                nearest[other] = nearest[node]
                queue.append(other)
    return nearest
