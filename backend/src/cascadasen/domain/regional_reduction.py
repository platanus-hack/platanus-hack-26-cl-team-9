"""Reduced regional network (docs/regional.md): the same idea as Chile's reduction (`cascade/network.py`).

One bus per substation (nearby substations and voltage levels merged), lines drawn as straight
segments between two buses with parallel circuits folded into one, and plants added up per bus.
Pure functions, no I/O. The sources give no line end points, so they are resolved here by snapping
each end of a line to the nearest bus; OSM ways are chained first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
import numpy as np

from cascadasen.domain.regional import RegionalBundle, RegionalSource

MERGE_KM = 3.0  # substations closer than this are one bus (assumption)
SNAP_KM = 12.0  # a line end closer than this to a bus belongs to it (assumption)
ATTACH_KM = 40.0  # a plant farther than this from every bus is dropped (assumption)
MIN_COMPONENT = 3  # connected pieces with fewer buses are noise (assumption)
JUNCTION_DIGITS = 3  # line ends without a substation within 0.001 degrees are the same point (about 110 m)


@dataclass
class RegionalBus:
    id: str
    name: str
    kv: float
    kv_levels: list[float]
    lon: float
    lat: float
    kind: str  # "substation" or "junction" (line meeting point with no substation)
    sources: list[str]
    records: list[str]
    merged: int = 1


@dataclass
class RegionalLink:
    id: str
    a: str
    b: str
    kv: float
    circuits: int | None
    length_km: float | None
    sources: list[str]
    records: list[str]
    merged: int = 1  # source lines folded into this one


@dataclass
class GenerationNode:
    id: str
    bus: str
    name: str
    lon: float
    lat: float
    mw: float
    tech: str | None  # technology with most MW
    mw_by_tech: dict[str, float]
    count: int
    sources: list[str]


@dataclass
class ReducedRegional:
    country: str
    country_name: str
    sources: list[RegionalSource]
    buses: list[RegionalBus] = field(default_factory=list)
    links: list[RegionalLink] = field(default_factory=list)
    generation: list[GenerationNode] = field(default_factory=list)
    raw_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Edge:
    u: Any
    v: Any
    kv: float
    circuits: int | None
    length_km: float | None
    sources: set[str]
    records: list[str]
    merged: int = 1


class _Union:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def join(self, i: int, j: int) -> None:
        self.parent[self.find(i)] = self.find(j)


def km_xy(lon: np.ndarray, lat: np.ndarray, lat0: float) -> np.ndarray:
    return np.c_[np.asarray(lon) * 111.32 * math.cos(math.radians(lat0)), np.asarray(lat) * 110.57]


def nearest(points: np.ndarray, targets: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Index and distance (km) of the nearest target for every point."""
    if len(targets) == 0:
        return np.zeros(len(points), dtype=int), np.full(len(points), np.inf)
    d = np.hypot(points[:, None, 0] - targets[None, :, 0], points[:, None, 1] - targets[None, :, 1])
    idx = d.argmin(axis=1)
    return idx, d[np.arange(len(points)), idx]


def _clusters(bundle: RegionalBundle, lat0: float) -> list[dict[str, Any]]:
    subs = bundle.substations
    if not subs:
        return []
    xy = km_xy([s.lon for s in subs], [s.lat for s in subs], lat0)
    dist = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
    union = _Union(len(subs))
    for i, j in np.argwhere(np.triu(dist < MERGE_KM, k=1)):
        union.join(int(i), int(j))
    groups: dict[int, list[int]] = {}
    for i in range(len(subs)):
        groups.setdefault(union.find(i), []).append(i)
    out = []
    for members in groups.values():
        top = max(members, key=lambda i: (subs[i].kv or 0, bool(subs[i].name)))
        levels = sorted({k for i in members for k in (subs[i].kv_levels or [subs[i].kv]) if k}, reverse=True)
        names = [subs[i].name for i in members if subs[i].name]
        out.append(
            {
                "name": subs[top].name or (names[0] if names else ""),
                "kv": max(levels) if levels else subs[top].kv,
                "levels": levels,
                "lon": subs[top].lon,
                "lat": subs[top].lat,
                "sources": sorted({subs[i].source for i in members}),
                "records": [subs[i].record for i in members],
                "merged": len(members),
            }
        )
    return out


def _contract(edges: dict[int, _Edge], adj: dict[Any, set[int]]) -> None:
    """Chain pass-through points and drop dangling ends, until nothing changes (OSM splits a line in many ways)."""
    changed = True
    while changed:
        changed = False
        for node in [n for n in adj if n[0] == "v"]:
            ids = adj.get(node)
            if ids is None:
                continue
            if len(ids) == 0:
                del adj[node]
            elif len(ids) == 1:  # dangling end that reaches no substation
                (eid,) = ids
                _remove(edges, adj, eid)
                del adj[node]
                changed = True
            elif len(ids) == 2:
                e1, e2 = sorted(ids)
                x = edges[e1].v if edges[e1].u == node else edges[e1].u
                y = edges[e2].v if edges[e2].u == node else edges[e2].u
                first, second = edges[e1], edges[e2]
                _remove(edges, adj, e1)
                _remove(edges, adj, e2)
                del adj[node]
                if x != y:
                    _add(edges, adj, _chain(first, second, x, y))
                changed = True


def _chain(a: _Edge, b: _Edge, x: Any, y: Any) -> _Edge:
    lengths = [e.length_km for e in (a, b) if e.length_km]
    circuits = [e.circuits for e in (a, b) if e.circuits]
    return _Edge(
        x,
        y,
        max(a.kv, b.kv),
        max(circuits) if circuits else None,
        sum(lengths) if lengths else None,
        a.sources | b.sources,
        a.records + b.records,
        a.merged + b.merged,
    )


def _remove(edges: dict[int, _Edge], adj: dict[Any, set[int]], eid: int) -> None:
    e = edges.pop(eid)
    for n in (e.u, e.v):
        if n in adj:
            adj[n].discard(eid)


def _add(edges: dict[int, _Edge], adj: dict[Any, set[int]], e: _Edge) -> None:
    eid = max(edges, default=-1) + 1
    edges[eid] = e
    adj.setdefault(e.u, set()).add(eid)
    adj.setdefault(e.v, set()).add(eid)


def reduce_bundle(bundle: RegionalBundle) -> ReducedRegional:
    """Normalised bundle -> buses, folded links and generation per bus."""
    out = ReducedRegional(
        bundle.country,
        bundle.country_name,
        list(bundle.sources),
        raw_counts={
            "lines": len(bundle.lines),
            "substations": len(bundle.substations),
            "plants": len(bundle.plants),
        },
        warnings=list(bundle.warnings),
    )
    if not bundle.lines:
        return out
    lat0 = float(np.mean([c[1] for ln in bundle.lines for c in ln.coords]))
    clusters = _clusters(bundle, lat0)
    cxy = km_xy([c["lon"] for c in clusters], [c["lat"] for c in clusters], lat0)

    # 1. every line end goes to the nearest bus within SNAP_KM, otherwise to a free point
    ends = np.array([[ln.coords[i][0], ln.coords[i][1]] for ln in bundle.lines for i in (0, -1)])
    near, near_km = nearest(km_xy(ends[:, 0], ends[:, 1], lat0), cxy)

    def node_of(k: int) -> Any:
        if near_km[k] <= SNAP_KM:
            return ("s", int(near[k]))
        return ("v", (round(float(ends[k, 0]), JUNCTION_DIGITS), round(float(ends[k, 1]), JUNCTION_DIGITS)))

    edges: dict[int, _Edge] = {}
    adj: dict[Any, set[int]] = {}
    loops = 0
    for i, ln in enumerate(bundle.lines):
        u, v = node_of(2 * i), node_of(2 * i + 1)
        if u == v:
            loops += 1
            continue
        _add(
            edges,
            adj,
            _Edge(u, v, ln.kv or 0.0, ln.circuits, ln.length_km, {ln.source}, [ln.record]),
        )
    # 2. chain pass-through points, drop dangling ends
    _contract(edges, adj)
    # 3. fold parallel lines between the same two buses
    folded: dict[frozenset, _Edge] = {}
    for e in edges.values():
        key = frozenset((e.u, e.v))
        if key in folded:
            f = folded[key]
            f.kv = max(f.kv, e.kv)
            f.circuits = (f.circuits or 1) + (e.circuits or 1)
            f.length_km = max(f.length_km or 0.0, e.length_km or 0.0) or None
            f.sources |= e.sources
            f.records += e.records
            f.merged += e.merged
        else:
            folded[key] = _Edge(
                e.u, e.v, e.kv, e.circuits, e.length_km, set(e.sources), list(e.records), e.merged
            )
    # 4. drop small pieces
    graph = nx.Graph()
    graph.add_edges_from((e.u, e.v) for e in folded.values())
    keep: set[Any] = set()
    small = 0
    for comp in nx.connected_components(graph):
        if len(comp) >= MIN_COMPONENT:
            keep |= comp
        else:
            small += len(comp)
    links = [e for e in folded.values() if e.u in keep]
    # 5. buses: substations that kept a line, plus junctions
    top_kv: dict[Any, float] = {}
    for e in links:
        for n in (e.u, e.v):
            top_kv[n] = max(top_kv.get(n, 0.0), e.kv)
    nodes = sorted(
        top_kv,
        key=lambda n: (
            -top_kv[n],
            clusters[n[1]]["name"] if n[0] == "s" else "~",
            n[1] if n[0] == "s" else 0,
            n[1] if n[0] == "v" else (0, 0),
        ),
    )
    bus_id: dict[Any, str] = {}
    for n in nodes:
        bus_id[n] = f"{bundle.country}-B{len(bus_id) + 1}"
        if n[0] == "s":
            c = clusters[n[1]]
            levels = sorted({*c["levels"], top_kv[n]}, reverse=True)
            out.buses.append(
                RegionalBus(
                    bus_id[n],
                    c["name"],
                    levels[0],
                    levels,
                    c["lon"],
                    c["lat"],
                    "substation",
                    c["sources"],
                    c["records"],
                    c["merged"],
                )
            )
        else:
            lon, lat = n[1]
            out.buses.append(RegionalBus(bus_id[n], "", top_kv[n], [top_kv[n]], lon, lat, "junction", [], []))
    for i, e in enumerate(sorted(links, key=lambda e: (-e.kv, bus_id[e.u], bus_id[e.v])), 1):
        a, b = sorted((bus_id[e.u], bus_id[e.v]))
        out.links.append(
            RegionalLink(
                f"{bundle.country}-R{i}",
                a,
                b,
                e.kv,
                e.circuits,
                round(e.length_km, 1) if e.length_km else None,
                sorted(e.sources),
                e.records[:20],
                e.merged,
            )
        )
    dropped_subs = len(clusters) - sum(1 for n in nodes if n[0] == "s")
    if loops:
        out.warnings.append(f"{loops} líneas con los dos extremos en la misma subestación descartadas")
    if small:
        out.warnings.append(f"{small} buses en piezas de menos de {MIN_COMPONENT} descartados")
    if dropped_subs:
        out.warnings.append(f"{dropped_subs} subestaciones sin ninguna línea resuelta descartadas")
    _attach_plants(bundle, out, lat0)
    return out


def _attach_plants(bundle: RegionalBundle, out: ReducedRegional, lat0: float) -> None:
    subs = [b for b in out.buses if b.kind == "substation"]
    if not subs or not bundle.plants:
        return
    sxy = km_xy([b.lon for b in subs], [b.lat for b in subs], lat0)
    pxy = km_xy([p.lon for p in bundle.plants], [p.lat for p in bundle.plants], lat0)
    near, km = nearest(pxy, sxy)
    per_bus: dict[int, list[int]] = {}
    lost_mw, lost = 0.0, 0
    for i, p in enumerate(bundle.plants):
        if km[i] <= ATTACH_KM:
            per_bus.setdefault(int(near[i]), []).append(i)
        else:
            lost += 1
            lost_mw += p.mw or 0.0
    for n, (bi, members) in enumerate(sorted(per_bus.items(), key=lambda kv: subs[kv[0]].id), 1):
        by_tech: dict[str, float] = {}
        for i in members:
            tech = bundle.plants[i].tech or "otra"
            by_tech[tech] = round(by_tech.get(tech, 0.0) + (bundle.plants[i].mw or 0.0), 2)
        top = max(by_tech, key=lambda t: by_tech[t])
        bus = subs[bi]
        out.generation.append(
            GenerationNode(
                f"{bundle.country}-G{n}",
                bus.id,
                bus.name,
                bus.lon,
                bus.lat,
                round(sum(by_tech.values()), 2),
                None if top == "otra" else top,
                dict(sorted(by_tech.items())),
                len(members),
                sorted({bundle.plants[i].source for i in members}),
            )
        )
    if lost:
        out.warnings.append(
            f"{lost} centrales ({lost_mw:,.0f} MW) a más de {ATTACH_KM:g} km de una subestación descartadas"
        )


def feature_collections(red: ReducedRegional) -> dict[str, dict[str, Any]]:
    """GeoJSON per layer: `lines` (straight between buses), `substations` (buses), `plants` (generation per bus)."""
    pos = {b.id: [round(b.lon, 5), round(b.lat, 5)] for b in red.buses}
    base = {"country": red.country, "is_assumption": False}
    lines = [
        {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [pos[ln.a], pos[ln.b]]},
            "properties": base
            | {
                "id": ln.id,
                "a": ln.a,
                "b": ln.b,
                "name": "",
                "kv": ln.kv,
                "circuits": ln.circuits,
                "length_km": ln.length_km,
                "source": "; ".join(ln.sources),
                "source_records": ln.records,
                "merged": ln.merged,
            },
        }
        for ln in red.links
    ]
    buses = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": pos[b.id]},
            "properties": base
            | {
                "id": b.id,
                "name": b.name,
                "kv": b.kv,
                "kv_levels": b.kv_levels,
                "kind": b.kind,
                "source": "; ".join(b.sources) or "derivado de líneas",
                "source_records": b.records,
                "merged": b.merged,
            },
        }
        for b in red.buses
    ]
    gen = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": pos[g.bus]},
            "properties": base
            | {
                "id": g.id,
                "bus": g.bus,
                "name": g.name,
                "tech": g.tech,
                "mw": g.mw,
                "mw_by_tech": g.mw_by_tech,
                "count": g.count,
                "source": "; ".join(g.sources),
            },
        }
        for g in red.generation
    ]
    wrap = lambda feats: {"type": "FeatureCollection", "features": feats}  # noqa: E731
    return {"lines": wrap(lines), "substations": wrap(buses), "plants": wrap(gen)}


def manifest_entry(red: ReducedRegional) -> dict[str, Any]:
    """Counts (reduced and raw), km per voltage and sources of one country."""
    km_by_kv: dict[str, float] = {}
    for ln in red.links:
        km_by_kv[f"{ln.kv:g}"] = round(km_by_kv.get(f"{ln.kv:g}", 0.0) + (ln.length_km or 0.0), 1)
    mw_by_tech: dict[str, float] = {}
    for g in red.generation:
        for tech, mw in g.mw_by_tech.items():
            mw_by_tech[tech] = round(mw_by_tech.get(tech, 0.0) + mw, 1)
    lons = [b.lon for b in red.buses]
    lats = [b.lat for b in red.buses]
    return {
        "country": red.country,
        "name": red.country_name,
        "counts": {"lines": len(red.links), "substations": len(red.buses), "plants": len(red.generation)},
        "raw_counts": red.raw_counts,
        "plant_count": sum(g.count for g in red.generation),
        "line_km_by_kv": dict(sorted(km_by_kv.items(), key=lambda kv: -float(kv[0]))),
        "plant_mw_by_tech": dict(sorted(mw_by_tech.items())),
        "bbox": [min(lons), min(lats), max(lons), max(lats)] if lons else None,
        "sources": [
            {
                "id": s.id,
                "name": s.name,
                "publisher": s.publisher,
                "url": s.url,
                "license": s.license,
                "attribution": s.attribution,
                "provides": list(s.provides),
                "fetched_at": s.fetched_at,
            }
            for s in red.sources
        ],
        "warnings": red.warnings,
    }
