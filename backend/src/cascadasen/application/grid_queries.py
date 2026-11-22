"""Read model over a GridSnapshot: filters, details, graph queries and GeoJSON layers."""

from __future__ import annotations

import dataclasses
import itertools
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

import networkx as nx

from cascadasen.domain.model import Edge, EdgeKind, GridSnapshot, Node, NodeKind
from cascadasen.domain.naming import norm

COUNTRY = "CHL"  # ISO3 of every element of the snapshot (Chile's SEN)


class NotFoundError(KeyError):
    pass


def _prov(items) -> list[dict]:
    return [dataclasses.asdict(p) for p in items]


class GridQueryService:
    def __init__(self, snapshot: GridSnapshot) -> None:
        self.s = snapshot
        self.nodes = {n.id: n for n in snapshot.nodes}
        self.edges = {e.id: e for e in snapshot.edges}
        self.incident: dict[str, list[Edge]] = defaultdict(list)
        for e in snapshot.edges:
            self.incident[e.source_node].append(e)
            self.incident[e.target_node].append(e)
        self.plants_by_node = defaultdict(list)
        for p in snapshot.plants:
            self.plants_by_node[p.node].append(p)
        self.storage_by_node = defaultdict(list)
        for st in snapshot.storage:
            self.storage_by_node[st.node].append(st)
        self.comunas = {c.cut: c for c in snapshot.comunas}
        self.served_by_node: dict[str, list[tuple[Any, Any]]] = defaultdict(list)
        for c in snapshot.comunas:
            for sh in c.served_by:
                self.served_by_node[sh.node].append((c, sh))
        self.site_members = defaultdict(list)
        for n in snapshot.nodes:
            self.site_members[n.site or n.id].append(n)
        self.zones = {z.id: z for z in snapshot.macro_zones}
        self.branch_edges = {b.name: len(b.edges) for b in snapshot.model_branches}
        self.graph = nx.MultiGraph()
        self.graph.add_nodes_from(self.nodes)
        for e in snapshot.edges:
            self.graph.add_edge(e.source_node, e.target_node, key=e.id, km=e.length_km or 0.0)
        self.main_component = max(nx.connected_components(self.graph), key=len) if self.nodes else set()

    # ------------------------------------------------------------ summaries

    def node_summary(self, n: Node) -> dict[str, Any]:
        return {
            "id": n.id,
            "kind": n.kind.value,
            "name": n.name,
            "kv": n.kv,
            "kv_levels": n.kv_levels,
            "segment": n.segment,
            "system": n.system,
            "owner": n.owner,
            "region_code": n.region_code,
            "comuna_code": n.comuna_code,
            "macro_zone": n.macro_zone,
            "lon": n.lon,
            "lat": n.lat,
            "location_source": n.location_source,
            "component": n.component,
            "in_main_grid": n.id in self.main_component,
            "degree": n.degree,
            "delivers": n.delivers,
            "served_population": round(n.served_population),
            "served_households": round(n.served_households),
            "generation_mw": round(n.generation_mw, 1),
            "storage_mw": round(n.storage_mw, 1),
            "site": n.site,
        }

    def edge_summary(self, e: Edge) -> dict[str, Any]:
        a, b = self.nodes[e.source_node], self.nodes[e.target_node]
        el = e.electrical
        tramos = e.ids.get("cen_tramos") or []
        return {
            "id": e.id,
            "kind": e.kind.value,
            "name": e.name,
            "source": e.source_node,
            "target": e.target_node,
            "source_name": a.name,
            "target_name": b.name,
            "kv": e.kv,
            "circuit": e.circuit,
            "segment": e.segment,
            "system": e.system,
            "owner": e.owner,
            "length_km": e.length_km,
            "topology_source": e.topology_source,
            "geometry_source": e.geometry_source,
            "cen_tramos": len(tramos),
            "s_nom_mva": el.s_nom_mva if el else None,
            "x_ohm": el.x_ohm if el else None,
            "r_ohm": el.r_ohm if el else None,
            "corridor_edges": self.branch_edges.get(el.branch, 1) if el else None,
            "model_branch": el.branch if el else None,
            "is_assumption": e.is_assumption,
        }

    def plant_dict(self, p) -> dict[str, Any]:
        d = dataclasses.asdict(p)
        d["provenance"] = _prov(p.provenance)
        d["node_name"] = self.nodes[p.node].name if p.node in self.nodes else None
        return d

    def storage_dict(self, st) -> dict[str, Any]:
        d = dataclasses.asdict(st)
        d["provenance"] = _prov(st.provenance)
        return d

    # ------------------------------------------------------------- general

    def stats(self) -> dict[str, Any]:
        v = self.s.stats.get("validation", {})
        return {
            "built_at": self.s.built_at,
            "version": self.s.version,
            **{k: x for k, x in self.s.stats.items() if k != "validation"},
            "validation_summary": v.get("summary", {}),
        }

    def sources(self) -> list[dict[str, Any]]:
        return [dataclasses.asdict(x) for x in self.s.sources]

    def validation(self) -> dict[str, Any]:
        return self.s.stats.get("validation", {"summary": {}, "checks": []})

    # --------------------------------------------------------------- nodes

    def list_nodes(
        self,
        q: str | None = None,
        kind: str | None = None,
        kv_min: float | None = None,
        kv_max: float | None = None,
        segment: str | None = None,
        region: str | None = None,
        macro_zone: str | None = None,
        system: str | None = None,
        delivers: bool | None = None,
        located: bool | None = None,
        main_grid: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[dict]]:
        key = norm(q) if q else None
        out = []
        for n in self.s.nodes:
            if kind and n.kind.value != kind:
                continue
            if key and key not in norm(n.name):
                continue
            if kv_min is not None and (n.kv or 0) < kv_min:
                continue
            if kv_max is not None and (n.kv or 0) > kv_max:
                continue
            if segment and (n.segment or "") != segment:
                continue
            if region and n.region_code != region:
                continue
            if macro_zone and n.macro_zone != macro_zone:
                continue
            if system and (n.system or "") != system:
                continue
            if delivers is not None and n.delivers != delivers:
                continue
            if located is not None and n.located != located:
                continue
            if main_grid is not None and (n.id in self.main_component) != main_grid:
                continue
            out.append(n)
        out.sort(key=lambda n: (-(n.kv or 0), n.name))
        return len(out), [self.node_summary(n) for n in out[offset : offset + limit]]

    def node(self, node_id: str) -> Node:
        if node_id not in self.nodes:
            raise NotFoundError(node_id)
        return self.nodes[node_id]

    def node_detail(self, node_id: str) -> dict[str, Any]:
        n = self.node(node_id)
        conns = []
        for e in self.incident.get(n.id, []):
            other = e.target_node if e.source_node == n.id else e.source_node
            conns.append({**self.edge_summary(e), "neighbor": other, "neighbor_name": self.nodes[other].name})
        conns.sort(key=lambda c: (-(c["kv"] or 0), c["neighbor_name"]))
        members = self.site_members.get(n.site or n.id, [n])
        plants = [self.plant_dict(p) for m in members for p in self.plants_by_node.get(m.id, [])]
        storage = [self.storage_dict(st) for m in members for st in self.storage_by_node.get(m.id, [])]
        served = [
            {
                "cut": c.cut,
                "name": c.name,
                "region": c.region_name,
                "population": round(sh.population),
                "households": round(sh.households),
                "share_of_comuna": sh.share,
            }
            for c, sh in self.served_by_node.get(n.id, [])
        ]
        served.sort(key=lambda x: -x["population"])
        tech = defaultdict(float)
        for p in plants:
            if p["operating"]:
                tech[p["tech"]] += p["mw"]
        return {
            **self.node_summary(n),
            "ids": n.ids,
            "provenance": _prov(n.provenance),
            "connections": conns,
            "site_members": [m.id for m in members if m.id != n.id],
            "plants": plants,
            "generation_by_tech_mw": {k: round(v, 1) for k, v in sorted(tech.items(), key=lambda t: -t[1])},
            "storage": storage,
            "served_comunas": served,
            "macro_zone_name": self.zones[n.macro_zone].name if n.macro_zone in self.zones else None,
        }

    # --------------------------------------------------------------- edges

    def list_edges(
        self,
        kind: str | None = None,
        kv_min: float | None = None,
        kv_max: float | None = None,
        segment: str | None = None,
        topology_source: str | None = None,
        with_electrical: bool | None = None,
        node: str | None = None,
        q: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[int, list[dict]]:
        key = norm(q) if q else None
        out = []
        for e in self.s.edges:
            if kind and e.kind.value != kind:
                continue
            if kv_min is not None and (e.kv or 0) < kv_min:
                continue
            if kv_max is not None and (e.kv or 0) > kv_max:
                continue
            if segment and (e.segment or "") != segment:
                continue
            if topology_source and topology_source.lower() not in e.topology_source.lower():
                continue
            if with_electrical is not None and (e.electrical is not None) != with_electrical:
                continue
            if node and node not in (e.source_node, e.target_node):
                continue
            if key and key not in norm(e.name):
                continue
            out.append(e)
        out.sort(key=lambda e: (-(e.kv or 0), e.name))
        return len(out), [self.edge_summary(e) for e in out[offset : offset + limit]]

    def edge_detail(self, edge_id: str) -> dict[str, Any]:
        if edge_id not in self.edges:
            raise NotFoundError(edge_id)
        e = self.edges[edge_id]
        return {
            **self.edge_summary(e),
            "electrical": dataclasses.asdict(e.electrical) if e.electrical else None,
            "ids": e.ids,
            "coords": e.coords,
            "provenance": _prov(e.provenance),
        }

    # ------------------------------------------------------- plants, storage

    def list_plants(
        self, tech=None, min_mw=None, operating=None, system=None, node=None, limit=2000, offset=0
    ):
        out = [
            p
            for p in self.s.plants
            if (not tech or p.tech == tech)
            and (min_mw is None or p.mw >= min_mw)
            and (operating is None or p.operating == operating)
            and (not system or p.system == system)
            and (not node or p.node == node)
        ]
        out.sort(key=lambda p: -p.mw)
        return len(out), [self.plant_dict(p) for p in out[offset : offset + limit]]

    def list_storage(self, source=None, existing_only: bool = False, limit=2000, offset=0):
        out = [
            st
            for st in self.s.storage
            if (not source or st.source == source) and (not existing_only or (st.build_year or 0) <= 2026)
        ]
        return len(out), [self.storage_dict(st) for st in out[offset : offset + limit]]

    # ------------------------------------------------------- comunas, zones

    def comuna_dict(self, c, geometry: bool = False) -> dict[str, Any]:
        d = {
            "cut": c.cut,
            "name": c.name,
            "region_code": c.region_code,
            "region": c.region_name,
            "province": c.province_name,
            "population": c.population,
            "households": c.households,
            "dwellings": c.dwellings,
            "centroid": c.centroid,
            "macro_zone": c.macro_zone,
            "served_by": [
                {
                    "node": sh.node,
                    "node_name": self.nodes[sh.node].name,
                    "population": round(sh.population),
                    "share": sh.share,
                    "kv": self.nodes[sh.node].kv,
                }
                for sh in c.served_by
            ],
        }
        if geometry:
            d["geometry"] = self.s.comuna_geometry.get(c.cut)
        return d

    def list_comunas(self, region=None, macro_zone=None) -> list[dict]:
        return [
            self.comuna_dict(c)
            for c in self.s.comunas
            if (not region or c.region_code == region) and (not macro_zone or c.macro_zone == macro_zone)
        ]

    def comuna_detail(self, cut: str) -> dict[str, Any]:
        if cut not in self.comunas:
            raise NotFoundError(cut)
        return self.comuna_dict(self.comunas[cut], geometry=True)

    def interzone_links(self) -> list[dict[str, Any]]:
        agg: dict[tuple, dict] = {}
        for e in self.s.edges:
            if e.kind != EdgeKind.LINE:
                continue
            za, zb = self.nodes[e.source_node].macro_zone, self.nodes[e.target_node].macro_zone
            if not za or not zb or za == zb:
                continue
            key = tuple(sorted((za, zb)))
            d = agg.setdefault(
                key,
                {
                    "zones": list(key),
                    "lines": 0,
                    "kv": set(),
                    "s_nom_mva_known": 0.0,
                    "lines_with_capacity": 0,
                    "_branches": set(),
                    "edges": [],
                },
            )
            d["lines"] += 1
            d["kv"].add(e.kv)
            d["edges"].append(e.id)
            if e.electrical and e.electrical.s_nom_mva:
                d["lines_with_capacity"] += 1
                if e.electrical.branch not in d["_branches"]:  # parallel lines share one corridor value
                    d["_branches"].add(e.electrical.branch)
                    d["s_nom_mva_known"] += e.electrical.s_nom_mva
        out = []
        for d in agg.values():
            d["model_branches"] = sorted(d.pop("_branches"))
            d["kv"] = sorted(k for k in d["kv"] if k)
            d["zone_names"] = [self.zones[z].name for z in d["zones"] if z in self.zones]
            out.append(d)
        return sorted(out, key=lambda d: -max(d["kv"] or [0]))

    def macro_zones(self) -> dict[str, Any]:
        return {"zones": [dataclasses.asdict(z) for z in self.s.macro_zones], "links": self.interzone_links()}

    # ---------------------------------------------------------------- graph

    def neighbors(self, node_id: str, depth: int = 1) -> dict[str, Any]:
        self.node(node_id)
        lengths = nx.single_source_shortest_path_length(self.graph, node_id, cutoff=max(1, min(depth, 5)))
        ids = set(lengths)
        edges = {k for u, v, k in self.graph.edges(ids, keys=True) if u in ids and v in ids}
        return {
            "center": node_id,
            "nodes": [
                {**self.node_summary(self.nodes[i]), "hops": lengths[i]} for i in sorted(ids, key=lengths.get)
            ],
            "edges": [self.edge_summary(self.edges[k]) for k in sorted(edges)],
        }

    def path(self, source: str, target: str) -> dict[str, Any]:
        self.node(source)
        self.node(target)
        simple = nx.Graph()
        for u, v, d in self.graph.edges(data=True):
            if not simple.has_edge(u, v) or d["km"] < simple[u][v]["km"]:
                simple.add_edge(u, v, km=d["km"])
        try:
            p = nx.shortest_path(simple, source, target, weight="km")
        except nx.NetworkXNoPath:
            return {"source": source, "target": target, "found": False, "nodes": [], "edges": [], "km": None}
        hops = []
        for u, v in itertools.pairwise(p):
            cand = [self.edges[k] for k in self.graph[u][v]]
            hops.append(min(cand, key=lambda e: e.length_km or 0))
        return {
            "source": source,
            "target": target,
            "found": True,
            "km": round(sum(e.length_km or 0 for e in hops), 1),
            "nodes": [self.node_summary(self.nodes[i]) for i in p],
            "edges": [self.edge_summary(e) for e in hops],
        }

    def islands(self, remove: Iterable[str]) -> dict[str, Any]:
        """Connectivity after removing edges or nodes. No power flow: an island without
        generation is reported as de-energized, an island with generation as 'may survive'."""
        remove = list(dict.fromkeys(remove))
        unknown = [x for x in remove if x not in self.edges and x not in self.nodes]
        if unknown:
            raise NotFoundError(", ".join(unknown))
        g = self.graph.copy()
        for x in remove:
            if x in self.edges:
                e = self.edges[x]
                if g.has_edge(e.source_node, e.target_node, key=x):
                    g.remove_edge(e.source_node, e.target_node, key=x)
            else:
                g.remove_node(x)
        comps = [c for c in nx.connected_components(g) if c & self.main_component]
        comps.sort(key=len, reverse=True)
        islands = []
        for k, c in enumerate(comps):
            ns = [self.nodes[i] for i in c]
            gen = sum(n.generation_mw for n in ns)
            pop = sum(n.served_population for n in ns)
            islands.append(
                {
                    "id": k,
                    "nodes": len(ns),
                    "substations": sum(1 for n in ns if n.kind == NodeKind.SUBSTATION),
                    "generation_mw": round(gen, 1),
                    "served_population": round(pop),
                    "macro_zones": sorted({n.macro_zone for n in ns if n.macro_zone}),
                    "state": "red principal"
                    if k == 0
                    else (
                        "sin generación: sin suministro"
                        if gen <= 0
                        else "isla con generación: puede sobrevivir"
                    ),
                    "node_ids": sorted(c) if k else [],
                    "sample": [n.name for n in sorted(ns, key=lambda n: -(n.kv or 0))[:6]],
                }
            )
        dark = sum(i["served_population"] for i in islands[1:] if i["generation_mw"] <= 0)
        return {
            "removed": remove,
            "islands": islands,
            "new_islands": max(0, len(islands) - 1),
            "population_without_supply": dark,
            "note": "Análisis de conectividad, sin flujo de potencia ni dinámica de frecuencia.",
        }

    # ------------------------------------------------------- electrical model

    def model_buses(self) -> list[dict]:
        return [dataclasses.asdict(b) for b in self.s.model_buses]

    def model_branches(self) -> list[dict]:
        return [dataclasses.asdict(b) for b in self.s.model_branches]

    # ------------------------------------------------------------- geojson

    def geojson(self, layer: str, kv_min: float | None = None) -> dict[str, Any]:
        feats: list[dict] = []
        if layer in ("substations", "nodes", "taps"):
            for n in self.s.nodes:
                if not n.located:
                    continue
                if layer == "substations" and n.kind != NodeKind.SUBSTATION:
                    continue
                if layer == "taps" and n.kind == NodeKind.SUBSTATION:
                    continue
                if kv_min is not None and (n.kv or 0) < kv_min:
                    continue
                feats.append(_point(n.lon, n.lat, self.node_summary(n)))
        elif layer == "lines":
            for e in self.s.edges:
                if not e.coords or (kv_min is not None and (e.kv or 0) < kv_min):
                    continue
                feats.append(
                    {
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": e.coords},
                        "properties": self.edge_summary(e),
                    }
                )
        elif layer == "plants":
            for p in self.s.plants:
                feats.append(
                    _point(
                        p.lon,
                        p.lat,
                        {
                            k: v
                            for k, v in self.plant_dict(p).items()
                            if k not in ("provenance", "model_units")
                        },
                    )
                )
        elif layer == "storage":
            for st in self.s.storage:
                if st.lon is not None:
                    feats.append(
                        _point(
                            st.lon,
                            st.lat,
                            {k: v for k, v in self.storage_dict(st).items() if k != "provenance"},
                        )
                    )
        elif layer == "comunas":
            for c in self.s.comunas:
                geom = self.s.comuna_geometry.get(c.cut)
                if not geom:
                    continue
                top = c.served_by[0].node if c.served_by else None
                feats.append(
                    {
                        "type": "Feature",
                        "geometry": geom,
                        "properties": {
                            "cut": c.cut,
                            "name": c.name,
                            "region": c.region_name,
                            "population": c.population,
                            "macro_zone": c.macro_zone,
                            "main_node": top,
                            "served_by": [[sh.node, sh.share] for sh in c.served_by],
                        },
                    }
                )
        else:
            raise NotFoundError(layer)
        # Same provenance field as data/processed/latam (docs/regional.md section 2): the snapshot is Chile's SEN.
        for f in feats:
            f["properties"]["country"] = COUNTRY
        return {"type": "FeatureCollection", "features": feats}


def _point(lon: float, lat: float, props: dict) -> dict:
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}
