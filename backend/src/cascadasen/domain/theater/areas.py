"""Operating areas over the mapa 3 network (docs/strategy.md 2.1, docs/mapa3.md).

The strategic theatre runs on the same reduced network the mapa 3 viewer draws: 188 buses (`B###`,
one per substation) and 273 lines (`R###`) from `domain/cascade/network.py`. Agents and the adversary
reason about 13 operating areas; each area is the set of buses inside a latitude band
(`domain/simulation/params/network.yaml`). A corridor is the set of lines that cross the boundary
between two areas. Defence functions are the two EDAC zones of the CEN 25F tables.

`resolve` maps any id the viewer knows (area, zone, corridor, `B###`, `R###`, or a real `SE...`
node id behind a bus) to the area or corridor it belongs to.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from functools import cached_property

import numpy as np

from cascadasen.domain.cascade.network import ReducedNetwork as BusNetwork
from cascadasen.domain.cascade.network import bus_id
from cascadasen.domain.simulation.network import AreaGraph, NetworkSpec, band_of

EDAC_ZONES = ("norte_grande", "centro_sur")


class UnknownTargetError(KeyError):
    pass


@dataclass(frozen=True)
class Area:
    id: str
    name: str
    zone: str
    index: int
    buses: tuple[int, ...]
    lat: float | None
    lon: float | None
    population: float
    anchor_bus: int | None  # largest load: where a crew is drawn on the map

    @property
    def bus_ids(self) -> list[str]:
        return [bus_id(b) for b in self.buses]


@dataclass(frozen=True)
class Corridor:
    id: str  # "A06-A07"
    a: str
    b: str
    lines: tuple[str, ...]  # R### crossing the boundary

    @property
    def members(self) -> tuple[str, ...]:
        return self.lines


@dataclass(frozen=True)
class Resolved:
    kind: str  # area | zone | corridor | bus | line | defense
    id: str
    area: str | None
    corridor: str | None
    input: str
    note: str = ""


@dataclass
class TheaterNetwork(AreaGraph[Area, Corridor]):
    buses: BusNetwork
    areas: dict[str, Area]
    corridors: dict[str, Corridor]
    area_of_bus: list[str]
    line_corridor: dict[str, str] = field(default_factory=dict)  # R### -> corridor (crossing lines only)
    line_area: dict[str, str] = field(default_factory=dict)  # R### -> area (internal lines)
    node_bus: dict[str, int] = field(default_factory=dict)  # real SE... id -> bus

    @cached_property
    def area_index(self) -> tuple[np.ndarray, list[str]]:
        """Area number of every bus and the area names, for vectorised sums per area."""
        names = list(self.areas)
        pos = {a: k for k, a in enumerate(names)}
        return np.array([pos[a] for a in self.area_of_bus], dtype=int), names

    def bus_lines(self, bus: int) -> list[str]:
        return [ln.id for ln in self.buses.lines if bus in (ln.a, ln.b)]

    def area_lines(self, area: str) -> list[str]:
        """Every line with at least one end in the area."""
        mine = set(self.areas[area].buses)
        return [ln.id for ln in self.buses.lines if ln.a in mine or ln.b in mine]

    def sites_of(self, target: str) -> list[str] | None:
        """Areas where a crew acts on an area or a corridor; None for any other target (the caller's fallback)."""
        if target in self.areas:
            return [target]
        if target in self.corridors:
            return [self.corridors[target].a, self.corridors[target].b]
        return None

    def defense_areas(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {f"edac:{z}": [] for z in EDAC_ZONES}
        for a in self.order:
            for z in {self.buses.zone(b) for b in self.areas[a].buses}:
                out[f"edac:{z}"].append(a)
        return out

    def resolve(self, target: str) -> Resolved:
        if target in self.areas:
            return Resolved("area", target, target, None, target)
        if target in self.zones:
            return Resolved("zone", target, None, None, target)
        if target in self.corridors:
            return Resolved("corridor", target, None, target, target)
        bus = self._bus(target)
        if bus is not None:
            area = self.area_of_bus[bus]
            name = self.buses.names[bus]
            return Resolved("bus", bus_id(bus), area, None, target, f"{name} ({self.areas[area].name})")
        if target in self.line_corridor:
            cid = self.line_corridor[target]
            return Resolved("line", target, None, cid, target, f"línea del corredor {cid}")
        if target in self.line_area:
            return Resolved("line", target, self.line_area[target], None, target, "línea interna del área")
        raise UnknownTargetError(target)

    def _bus(self, target: str) -> int | None:
        if len(target) == 4 and target[0] == "B" and target[1:].isdigit():
            i = int(target[1:])
            return i if i < self.buses.size else None
        return self.node_bus.get(target)


def build_theater_network(
    buses: BusNetwork, people: np.ndarray, load: np.ndarray, spec: NetworkSpec | None = None
) -> TheaterNetwork:
    """Group the mapa 3 buses into operating areas by latitude band and find the corridors."""
    specs = (spec or NetworkSpec.default()).areas
    area_of_bus = [band_of(buses.lat[i], specs) for i in range(buses.size)]
    members: dict[str, list[int]] = defaultdict(list)
    for i, a in enumerate(area_of_bus):
        members[a].append(i)
    areas = {}
    for idx, s in enumerate(specs):
        ids = tuple(members.get(s.id, ()))
        if not ids:
            continue
        lat = float(np.mean([buses.lat[i] for i in ids]))
        lon = float(np.mean([buses.lon[i] for i in ids]))
        anchor = max(ids, key=lambda i: (float(load[i]), -i))
        areas[s.id] = Area(
            s.id, s.name, s.zone, idx, ids, lat, lon, float(sum(people[i] for i in ids)), anchor
        )
    crossing: dict[tuple[str, str], list[str]] = defaultdict(list)
    line_area = {}
    order = {s.id: k for k, s in enumerate(specs)}
    for ln in buses.lines:
        a, b = area_of_bus[ln.a], area_of_bus[ln.b]
        if a == b:
            line_area[ln.id] = a
        else:
            pair = tuple(sorted((a, b), key=order.__getitem__))
            crossing[pair].append(ln.id)
    corridors = {
        f"{a}-{b}": Corridor(f"{a}-{b}", a, b, tuple(sorted(ids))) for (a, b), ids in sorted(crossing.items())
    }
    line_corridor = {lid: c.id for c in corridors.values() for lid in c.lines}
    node_bus = {node: i for i in range(buses.size) for node in buses.map_nodes[i]}
    return TheaterNetwork(buses, areas, corridors, area_of_bus, line_corridor, line_area, node_bus)
