"""Reduced network: one bus per substation, only lines.

Why: transformers and voltage levels inside a substation do not change where a cut isolates power, and
the engine has no reactive power. Merging them gives about 190 buses and 275 lines, each with a MW limit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SUBSTATION = re.compile(r"^(.*?)_(\d+(?:\.\d+)?)(?:_.*)?$")
X_MIN_PU = (
    5e-4  # assumption: near-zero reactances (ties) are raised to this so the DC system stays well conditioned
)
NORTE_GRANDE_MAX_LAT = (
    -26.0
)  # Arica, Tarapacá and Antofagasta; everything south counts as centro-sur (NTSyCS EDAC tables)


def substation_of(bus_name: str) -> str:
    """'S/E ALTO JAHUEL_500' -> 'S/E ALTO JAHUEL' (also handles '_154_II' style suffixes)."""
    match = _SUBSTATION.match(bus_name)
    return match.group(1) if match else bus_name


@dataclass(frozen=True)
class Line:
    id: str
    a: int
    b: int
    capacity_mw: float
    x_pu: float
    kv: float
    branches: tuple[str, ...]  # PyPSA-CL branches folded into this line
    map_edges: tuple[str, ...]  # map line ids (lines.geojson) behind it
    country: str = "CHL"  # ISO 3166-1 alpha-3, as in data/processed/latam (docs/regional.md)


@dataclass
class ReducedNetwork:
    names: list[str]
    lat: list[float]
    lon: list[float]
    kv: list[float]
    model_buses: list[list[str]]
    map_nodes: list[list[str]]
    lines: list[Line]
    index: dict[str, int]
    bus_of_model_bus: dict[str, int]
    country: str = "CHL"  # ISO3 of every bus; a reduced network never spans two countries

    @property
    def size(self) -> int:
        return len(self.names)

    def zone(self, bus: int) -> str:
        return "norte_grande" if self.lat[bus] > NORTE_GRANDE_MAX_LAT else "centro_sur"


def reduce_network(snapshot: dict, year: int | None = None) -> ReducedNetwork:
    """year: keep only branches built by then (PyPSA-CL has two 2029 links, one of them the Kimal-Lo Aguirre HVDC)."""
    buses = snapshot["model_buses"]
    index: dict[str, int] = {}
    members: list[list[dict]] = []
    for b in sorted(buses, key=lambda b: substation_of(b["name"])):
        key = substation_of(b["name"])
        if key not in index:
            index[key] = len(members)
            members.append([])
        members[index[key]].append(b)
    bus_of = {b["name"]: index[substation_of(b["name"])] for b in buses}
    top = [max(m, key=lambda b: b["kv"]) for m in members]
    return ReducedNetwork(
        names=list(index),
        lat=[b["lat"] for b in top],
        lon=[b["lon"] for b in top],
        kv=[b["kv"] for b in top],
        model_buses=[[b["name"] for b in m] for m in members],
        map_nodes=[sorted({b["node"] for b in m if b["node"]}) for m in members],
        lines=_fold_lines(_built_by(snapshot["model_branches"], year), bus_of),
        index=index,
        bus_of_model_bus=bus_of,
    )


def _built_by(branches: list[dict], year: int | None) -> list[dict]:
    return [r for r in branches if year is None or (r.get("build_year") or 0) <= year]


def _fold_lines(branches: list[dict], bus_of: dict[str, int]) -> list[Line]:
    groups: dict[tuple[int, int], list[dict]] = {}
    for r in branches:
        a, b = bus_of[r["bus0"]], bus_of[r["bus1"]]
        if a != b:  # same substation: a transformer (or tie), folded away
            groups.setdefault((min(a, b), max(a, b)), []).append(r)
    return [_parallel(f"R{i:03d}", pair, rows) for i, (pair, rows) in enumerate(sorted(groups.items()))]


def _parallel(line_id: str, pair: tuple[int, int], rows: list[dict]) -> Line:
    admittance = sum(1.0 / r["x_pu"] for r in rows)
    return Line(
        id=line_id,
        a=pair[0],
        b=pair[1],
        capacity_mw=sum(r["s_nom_mva"] for r in rows),
        x_pu=max(1.0 / admittance, X_MIN_PU),
        kv=max(r["kv"] for r in rows),
        branches=tuple(r["name"] for r in rows),
        map_edges=tuple(sorted({e for r in rows for e in (r.get("edges") or [])})),
    )
