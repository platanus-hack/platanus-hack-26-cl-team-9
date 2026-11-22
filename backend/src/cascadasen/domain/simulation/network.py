"""Reduced trunk network: operating areas aggregated from the unified grid snapshot.

Each area gathers every main-grid node inside a latitude band (docs/strategy.md section 2.1).
Lines crossing between areas become corridors; lines at or above `high_voltage_kv` and the rest
stay as separate corridors (docs/stack.md section 4.1). A corridor keeps its parts (one per
PyPSA-CL branch, or one per line without electrical data), so losing one substation removes only
the lines that end there. Reactance and capacity come from the PyPSA-CL branch when known, else
from typical values flagged `is_assumption`.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, cast

import networkx as nx

from cascadasen.domain.geo import haversine_km
from cascadasen.domain.model import Edge, EdgeKind, GridSnapshot, Node, NodeKind
from cascadasen.domain.simulation.params import Provenance, load_params, provenance, value
from cascadasen.domain.validation import X_PER_KM


class UnknownTargetError(KeyError):
    """A target id is neither an area, a corridor, nor a snapshot node or line of the network."""


@dataclass(frozen=True)
class AreaSpec:
    id: str
    name: str
    zone: str
    lat_south: float | None
    anchors: tuple[str, ...] = ()


@dataclass(frozen=True)
class NetworkSpec:
    areas: tuple[AreaSpec, ...]
    s_base_mva: float = 100.0
    high_voltage_kv: float = 400.0
    excluded_systems: frozenset[str] = frozenset()
    excluded_zones: frozenset[str] = frozenset()
    typical_capacity_mva: dict[float, float] = field(default_factory=lambda: {500.0: 1700.0, 220.0: 400.0})
    corridor_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)
    provenance: tuple[Provenance, ...] = ()

    @classmethod
    def default(cls) -> NetworkSpec:
        p = load_params("network")
        areas = tuple(
            AreaSpec(a["id"], a["name"], a["zone"], a.get("lat_south"), tuple(a.get("anchors", ())))
            for a in value(p["areas"], "areas")
        )
        return cls(
            areas=areas,
            s_base_mva=float(value(p["s_base_mva"])),
            high_voltage_kv=float(value(p["high_voltage_kv"])),
            excluded_systems=frozenset(p.get("excluded_systems", [])),
            excluded_zones=frozenset(p.get("excluded_zones", [])),
            typical_capacity_mva={float(k): float(v) for k, v in value(p["typical_capacity_mva"]).items()},
            corridor_overrides=dict(value(p["corridor_overrides"]) or {}),
            provenance=(
                provenance(p["areas"], "network.areas"),
                provenance(p["typical_capacity_mva"], "network.typical_capacity_mva"),
                provenance(p["corridor_overrides"], "network.corridor_overrides"),
            ),
        )


@dataclass(frozen=True)
class Area:
    id: str
    name: str
    zone: str
    index: int
    lon: float | None
    lat: float | None
    population: float
    installed_mw: dict[str, float]
    storage_mw: float
    aggregates: tuple[str, ...]
    anchors: tuple[str, ...]
    main_node: str | None


@dataclass(frozen=True)
class NodeInfo:
    id: str
    name: str
    area: str
    kind: str
    kv: float | None
    population: float
    generation_mw: dict[str, float]
    corridor_lines: tuple[str, ...]


@dataclass(frozen=True)
class CorridorPart:
    key: str
    x_pu: float
    capacity_mw: float
    members: tuple[str, ...]
    is_assumption: bool


@dataclass(frozen=True)
class Corridor:
    id: str
    a: str
    b: str
    kv_class: str
    parts: tuple[CorridorPart, ...]
    source: str
    override: dict[str, Any] = field(default_factory=dict)

    @property
    def members(self) -> tuple[str, ...]:
        return tuple(sorted(m for p in self.parts for m in p.members))

    @property
    def lines(self) -> int:
        return len(self.members)

    @property
    def is_assumption(self) -> bool:
        return bool(self.override) or any(p.is_assumption for p in self.parts)

    @property
    def x_pu(self) -> float:
        return self.effective(frozenset())[0]  # type: ignore[index]

    @property
    def capacity_mw(self) -> float:
        return self.effective(frozenset())[1]  # type: ignore[index]

    def effective(self, out_lines: frozenset[str] | set[str]) -> tuple[float, float] | None:
        """(x in pu, capacity in MW) with the given lines out, or None when no part remains.
        A part is lost when any of its member lines is out (segments in series)."""
        alive = [p for p in self.parts if not (set(p.members) & out_lines)]
        if not alive:
            return None
        y_all = sum(1.0 / p.x_pu for p in self.parts)
        y = sum(1.0 / p.x_pu for p in alive)
        cap_all = sum(p.capacity_mw for p in self.parts)
        cap = sum(p.capacity_mw for p in alive)
        x_full = float(self.override.get("x_pu", 1.0 / y_all))
        cap_full = float(self.override.get("capacity_mw", cap_all))
        return round(x_full * y_all / y, 6), round(cap_full * cap / cap_all, 1)


@dataclass(frozen=True)
class Resolved:
    kind: str  # "area" | "corridor" | "node" | "line"
    id: str
    area: str | None
    corridor: str | None
    input: str
    note: str = ""


@dataclass
class ReducedNetwork:
    areas: dict[str, Area]
    corridors: dict[str, Corridor]
    nodes: dict[str, NodeInfo]
    edge_corridor: dict[str, str]
    edge_area: dict[str, str]
    s_base_mva: float
    provenance: list[Provenance]

    @property
    def order(self) -> list[str]:
        return sorted(self.areas, key=lambda a: self.areas[a].index)

    @property
    def zones(self) -> list[str]:
        return list(dict.fromkeys(self.areas[a].zone for a in self.order))

    def zone_areas(self, zone: str) -> list[str]:
        return [a for a in self.order if self.areas[a].zone == zone]

    def incident(self, area: str) -> list[Corridor]:
        return [c for c in self.corridors.values() if area in (c.a, c.b)]

    def resolve(self, target: str) -> Resolved:
        """Map an area id, corridor id, snapshot node id or snapshot line id to a network element."""
        if target in self.areas:
            return Resolved("area", target, target, None, target)
        if target in self.corridors:
            return Resolved("corridor", target, None, target, target)
        if target in self.nodes:
            n = self.nodes[target]
            return Resolved("node", target, n.area, None, target, f"{n.name} ({self.areas[n.area].name})")
        if target in self.edge_corridor:
            cid = self.edge_corridor[target]
            return Resolved("line", target, None, cid, target, f"línea del corredor {cid}")
        if target in self.edge_area:
            return Resolved("line", target, self.edge_area[target], None, target, "línea interna del área")
        raise UnknownTargetError(target)


def _main_component(snapshot: GridSnapshot) -> set[str]:
    g = nx.Graph()
    g.add_nodes_from(n.id for n in snapshot.nodes)
    g.add_edges_from((e.source_node, e.target_node) for e in snapshot.edges)
    return max(nx.connected_components(g), key=len) if snapshot.nodes else set()


def _band(lat: float, specs: tuple[AreaSpec, ...]) -> str:
    for s in specs:
        if s.lat_south is None or lat >= s.lat_south:
            return s.id
    return specs[-1].id


def _nearest_class(kv: float, table: dict[float, Any]) -> float:
    return min(table, key=lambda k: abs(k - kv))


def build_reduced_network(snapshot: GridSnapshot, spec: NetworkSpec | None = None) -> ReducedNetwork:
    spec = spec or NetworkSpec.default()
    nodes = _eligible_nodes(snapshot, spec)
    node_area = _assign_areas(snapshot, spec, nodes)
    corridors, edge_corridor, edge_area = _corridors(snapshot, spec, node_area)
    areas = _build_areas(snapshot, spec, nodes, node_area, corridors)
    corridors = {k: c for k, c in corridors.items() if c.a in areas and c.b in areas}
    edge_corridor = {k: v for k, v in edge_corridor.items() if v in corridors}
    gen: dict[str, Counter] = defaultdict(Counter)
    for p in snapshot.plants:
        if p.operating and p.mw and p.node in node_area:
            gen[p.node][p.tech] += p.mw  # type: ignore[assignment]  # a Counter that holds MW (floats)
    node_lines: dict[str, list[str]] = defaultdict(list)
    for e in snapshot.edges:
        if e.id in edge_corridor:
            node_lines[e.source_node].append(e.id)
            node_lines[e.target_node].append(e.id)
    infos = {
        nid: NodeInfo(
            id=nid,
            name=nodes[nid].name,
            area=aid,
            kind=nodes[nid].kind.value,
            kv=nodes[nid].kv,
            population=round(nodes[nid].served_population),
            generation_mw={k: round(v, 1) for k, v in sorted(gen[nid].items())},
            corridor_lines=tuple(sorted(node_lines.get(nid, []))),
        )
        for nid, aid in node_area.items()
        if aid in areas
    }
    return ReducedNetwork(
        areas=areas,
        corridors=corridors,
        nodes=infos,
        edge_corridor=edge_corridor,
        edge_area={k: v for k, v in edge_area.items() if v in areas},
        s_base_mva=spec.s_base_mva,
        provenance=list(spec.provenance),
    )


def _eligible_nodes(snapshot: GridSnapshot, spec: NetworkSpec) -> dict[str, Node]:
    main = _main_component(snapshot)
    return {
        n.id: n
        for n in snapshot.nodes
        if n.id in main
        and (n.system or "") not in spec.excluded_systems
        and (n.macro_zone or "") not in spec.excluded_zones
    }


def _assign_areas(snapshot: GridSnapshot, spec: NetworkSpec, nodes: dict[str, Node]) -> dict[str, str]:
    """Located nodes go to their latitude band; unlocated ones take the majority area of their
    assigned neighbours, spreading outwards until nothing changes."""
    adj: dict[str, set[str]] = defaultdict(set)
    for e in snapshot.edges:
        if e.source_node in nodes and e.target_node in nodes:
            adj[e.source_node].add(e.target_node)
            adj[e.target_node].add(e.source_node)
    node_area = {n.id: _band(n.lat, spec.areas) for n in nodes.values() if n.lat is not None}
    pending = [nid for nid in nodes if nid not in node_area]
    while pending:
        votes = {nid: Counter(node_area[m] for m in adj[nid] if m in node_area) for nid in pending}
        decided = {nid: min(v.items(), key=lambda kv: (-kv[1], kv[0]))[0] for nid, v in votes.items() if v}
        if not decided:
            break
        node_area.update(decided)
        pending = [nid for nid in pending if nid not in decided]
    return node_area


def _main_node(ns: list[Node], corridors: dict[str, Corridor], snapshot_edges: dict[str, Edge]) -> str | None:
    """Backbone substation of an area: highest voltage, then most corridor lines."""
    ids = {n.id for n in ns}
    lines: Counter[str] = Counter()
    for c in corridors.values():
        for m in c.members:
            e = snapshot_edges[m]
            for end in (e.source_node, e.target_node):
                if end in ids:
                    lines[end] += 1
    subs = [n for n in ns if n.kind == NodeKind.SUBSTATION]
    if not subs:
        return None
    return max(subs, key=lambda n: (n.kv or 0, lines[n.id], n.served_population, n.id)).id


def _build_areas(
    snapshot: GridSnapshot,
    spec: NetworkSpec,
    nodes: dict[str, Node],
    node_area: dict[str, str],
    corridors: dict[str, Corridor],
) -> dict[str, Area]:
    members: dict[str, list[Node]] = defaultdict(list)
    for nid, aid in node_area.items():
        members[aid].append(nodes[nid])
    plants: dict[str, Counter] = defaultdict(Counter)
    for p in snapshot.plants:
        if p.operating and p.node in node_area and p.mw:
            plants[node_area[p.node]][p.tech] += p.mw  # type: ignore[assignment]  # a Counter that holds MW (floats)
    edges = {e.id: e for e in snapshot.edges}
    areas: dict[str, Area] = {}
    for idx, s in enumerate(spec.areas):
        ns = members.get(s.id, [])
        if not ns:
            continue
        hv = [n for n in ns if n.located and n.kind == NodeKind.SUBSTATION and (n.kv or 0) >= 220]
        pts = hv or [n for n in ns if n.located]
        areas[s.id] = Area(
            id=s.id,
            name=s.name,
            zone=s.zone,
            index=idx,
            lon=round(sum(cast(float, n.lon) for n in pts) / len(pts), 5) if pts else None,
            lat=round(sum(cast(float, n.lat) for n in pts) / len(pts), 5) if pts else None,
            population=round(sum(n.served_population for n in ns)),
            installed_mw={k: round(v, 1) for k, v in sorted(plants[s.id].items())},
            storage_mw=round(sum(n.storage_mw for n in ns), 1),
            aggregates=tuple(sorted(n.id for n in ns)),
            anchors=s.anchors,
            main_node=_main_node(ns, corridors, edges),
        )
    return areas


def _line_part(e: Edge, kv: float, spec: NetworkSpec, nodes: dict[str, Node]) -> CorridorPart | None:
    if e.kind == EdgeKind.COLOCATED:
        return CorridorPart(e.id, 0.001, 9999.0, (e.id,), True)
    el = e.electrical
    if el and el.x_ohm and el.s_nom_mva:
        return CorridorPart(el.branch, el.x_ohm * spec.s_base_mva / kv**2, el.s_nom_mva, (e.id,), False)
    km = e.length_km
    if not km:
        sa, sb = nodes[e.source_node], nodes[e.target_node]
        km = (
            haversine_km(cast(float, sa.lon), cast(float, sa.lat), cast(float, sb.lon), cast(float, sb.lat))
            if sa.located and sb.located
            else None
        )
    if not km:
        return None
    lo, hi = X_PER_KM[min(X_PER_KM, key=lambda k: abs(k - kv))]
    cap = spec.typical_capacity_mva[_nearest_class(kv, spec.typical_capacity_mva)]
    return CorridorPart(e.id, (lo + hi) / 2 * km * spec.s_base_mva / kv**2, cap, (e.id,), True)


def _corridors(
    snapshot: GridSnapshot, spec: NetworkSpec, node_area: dict[str, str]
) -> tuple[dict[str, Corridor], dict[str, str], dict[str, str]]:
    nodes = {n.id: n for n in snapshot.nodes}
    index = {s.id: i for i, s in enumerate(spec.areas)}
    groups: dict[tuple[str, str, str], dict[str, CorridorPart]] = {}
    edge_corridor: dict[str, str] = {}
    edge_area: dict[str, str] = {}
    for e in snapshot.edges:
        a, b = node_area.get(e.source_node), node_area.get(e.target_node)
        if a is None or b is None:
            continue
        if a == b:
            edge_area[e.id] = a
            continue
        if index[a] > index[b]:
            a, b = b, a
        kv = e.kv or 220.0
        part = _line_part(e, kv, spec, nodes)
        if part is None:
            continue
        cls = "500" if kv >= spec.high_voltage_kv else "220"
        parts = groups.setdefault((a, b, cls), {})
        prev = parts.get(part.key)
        if prev:  # several snapshot lines share one PyPSA-CL branch: count the branch once
            part = CorridorPart(
                prev.key, prev.x_pu, prev.capacity_mw, (*prev.members, e.id), prev.is_assumption
            )
        parts[part.key] = part
        edge_corridor[e.id] = f"{a}-{b}/{cls}"

    corridors: dict[str, Corridor] = {}
    for (a, b, cls), parts in sorted(groups.items(), key=lambda kv: (index[kv[0][0]], kv[0][2])):
        cid = f"{a}-{b}/{cls}"
        override = spec.corridor_overrides.get(cid, {})
        fallback = any(p.is_assumption for p in parts.values())
        source = "PyPSA-CL branches" + (" + typical values (X_PER_KM, typical capacity)" if fallback else "")
        if override:
            source += f"; override: {override.get('note', '')}"
        corridors[cid] = Corridor(cid, a, b, cls, tuple(parts[k] for k in sorted(parts)), source, override)
    return corridors, edge_corridor, edge_area
