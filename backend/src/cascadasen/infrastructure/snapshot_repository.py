"""JSON file repository for the unified grid snapshot (data/processed/)."""

from __future__ import annotations

import dataclasses
import json
from enum import Enum
from pathlib import Path
from typing import Any

from cascadasen.domain.model import (
    Comuna,
    Edge,
    EdgeKind,
    ElectricalParams,
    GridSnapshot,
    MacroZone,
    ModelBranch,
    ModelBus,
    Node,
    NodeKind,
    Plant,
    Provenance,
    ServiceShare,
    SourceInfo,
    Storage,
)
from cascadasen.infrastructure.files import write_json


def _plain(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        return {f.name: _plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_plain(v) for v in obj]
    if isinstance(obj, float):
        return round(obj, 6)
    return obj


def to_dict(s: GridSnapshot) -> dict[str, Any]:
    d = _plain(s)
    d.pop("comuna_geometry", None)
    return d


def from_dict(d: dict[str, Any], comuna_geometry: dict[str, Any] | None = None) -> GridSnapshot:
    def prov(items):
        return [Provenance(**p) for p in items or []]

    nodes = []
    for n in d["nodes"]:
        n = dict(n)
        n["kind"] = NodeKind(n["kind"])
        n["provenance"] = prov(n.get("provenance"))
        nodes.append(Node(**n))
    edges = []
    for e in d["edges"]:
        e = dict(e)
        e["kind"] = EdgeKind(e["kind"])
        e["provenance"] = prov(e.get("provenance"))
        e["electrical"] = ElectricalParams(**e["electrical"]) if e.get("electrical") else None
        e["coords"] = [tuple(c) for c in e["coords"]] if e.get("coords") else None
        edges.append(Edge(**e))
    plants = [Plant(**{**p, "provenance": prov(p.get("provenance"))}) for p in d["plants"]]
    storage = [Storage(**{**s, "provenance": prov(s.get("provenance"))}) for s in d["storage"]]
    comunas = []
    for c in d["comunas"]:
        c = dict(c)
        c["served_by"] = [ServiceShare(**x) for x in c.get("served_by") or []]
        c["centroid"] = tuple(c["centroid"]) if c.get("centroid") else None
        comunas.append(Comuna(**c))
    return GridSnapshot(
        version=d["version"],
        built_at=d["built_at"],
        sources=[SourceInfo(**{**s, "provides": tuple(s["provides"])}) for s in d["sources"]],
        nodes=nodes,
        edges=edges,
        plants=plants,
        storage=storage,
        comunas=comunas,
        macro_zones=[MacroZone(**{**z, "color": tuple(z["color"])}) for z in d["macro_zones"]],
        model_buses=[ModelBus(**b) for b in d["model_buses"]],
        model_branches=[ModelBranch(**b) for b in d["model_branches"]],
        stats=d["stats"],
        assumptions=d["assumptions"],
        comuna_geometry=comuna_geometry or {},
    )


class JsonSnapshotRepository:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.geometry_path = path.with_name("comunas_geometry.json")

    def save(self, snapshot: GridSnapshot) -> None:
        write_json(self.path, to_dict(snapshot))
        write_json(self.geometry_path, snapshot.comuna_geometry)

    def load(self) -> GridSnapshot | None:
        if not self.path.exists():
            return None
        geometry = (
            json.loads(self.geometry_path.read_text(encoding="utf-8"))
            if self.geometry_path.exists()
            else None
        )
        return from_dict(json.loads(self.path.read_text(encoding="utf-8")), geometry)
