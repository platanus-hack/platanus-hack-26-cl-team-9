"""Merge every source into one grid snapshot. Pure function of the SourceBundle.

Steps
1. Substations: IDE Energía (coordinates) joined to CEN Infotecnica by id (IDE carries the CEN id
   as ID_SUBEST); busbars add voltage levels; CEN-only substations take coordinates from the
   PyPSA-CL bus of the same name when one exists.
2. Lines: topology inferred from IDE geometry (see topology_inference), then reconciled with the
   official CEN sections (tramos): matching sections confirm the edge and add circuit and owner
   data; sections with no geometric counterpart are added as schematic straight edges.
3. Adjacent substations (< site_m) form a site joined by assumed couplings.
4. Electrical parameters from the PyPSA-CL model are attached to the edges of each corridor.
5. Plants and storage are attached to nodes (declared model bus > substation name > nearest).
6. Population: each urban census zone goes to its nearest delivery substation; the rural
   remainder of each comuna goes to the delivery substations inside it (or the nearest one).
"""

from __future__ import annotations

import itertools
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

import networkx as nx
import numpy as np

from cascadasen.domain.geo import PointIndex, haversine_km, project, simplify
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
    RawPlant,
    ServiceShare,
    SourceBundle,
    Storage,
)
from cascadasen.domain.naming import ascii_upper, bay_stripped, is_tap_name, norm, parse_kv, similarity
from cascadasen.domain.topology_inference import InferenceConfig, infer_line_topology

SNAPSHOT_VERSION = 2

MACRO_ZONES = [
    MacroZone("NG", "Norte Grande", ["15", "01", "02"], (214, 140, 69)),
    MacroZone("NC", "Norte Chico", ["03", "04"], (196, 168, 70)),
    MacroZone("CE", "Centro", ["05", "13", "06"], (88, 160, 196)),
    MacroZone("CS", "Centro-Sur", ["07", "16", "08"], (92, 170, 120)),
    MacroZone("SU", "Sur", ["09", "14", "10"], (64, 132, 110)),
    MacroZone("AY", "Aysén (SEA)", ["11"], (132, 110, 180)),
    MacroZone("MA", "Magallanes (SEM)", ["12"], (160, 104, 150)),
]
REGION_TO_MACRO = {r: z.id for z in MACRO_ZONES for r in z.region_codes}
MEDIUM_SYSTEM_BY_REGION = {"11": "SEA", "12": "SEM"}  # Aysén and Magallanes are separate medium systems

PLANT_PREFIX_RE = re.compile(
    r"^(TER|HE|HP|PFV|PE|PMGD|CSP|GEO|BIO|MINI HIDRO|CENTRAL|PARQUE EOLICO|PARQUE SOLAR)\s+"
)
SE_CODE_RE = re.compile(r"(SE\d{3}[A-Z]\d{4})")


@dataclass(frozen=True)
class UnifyConfig:
    site_m: float = 250.0
    simplify_m: float = 60.0
    plant_name_m: float = 25000.0
    plant_near_m: float = 30000.0
    model_gen_m: float = 3000.0
    bus_match_m: float = 6000.0
    name_ok: float = 0.82
    current_year: int = 2026


class GridUnifier:
    def __init__(self, cfg: UnifyConfig | None = None, inference: InferenceConfig | None = None) -> None:
        self.cfg = cfg or UnifyConfig()
        self.inference = inference or InferenceConfig()
        self.stats: dict = {}
        self.assumptions: list[str] = []

    # ------------------------------------------------------------------ public

    def unify(self, b: SourceBundle) -> GridSnapshot:
        """Build the `GridSnapshot` from the raw source bundle. The order follows the data dependencies.

        Substations first (joined by CEN id), then the ones without coordinates are located from the PyPSA-CL
        model. Line topology is inferred from geometry and names, then reconciled with the official CEN sections
        (which adds edges). The site links come next, then the electrical parameters (they need the edges), then
        plants and storage (they need the model buses). Generation and storage are summed per node, service areas
        and macro zones follow (they need the generation), and last the edge geometry is simplified, so that
        inference worked on the full-resolution lines. Stats and assumptions accumulate on the instance. Apart
        from `built_at`, the result is a pure function of the bundle."""
        nodes = self._substations(b)
        by_id = {n.id: n for n in nodes}
        self._locate_from_model(b, nodes)

        inferred = infer_line_topology(nodes, b.geo_lines, self.inference)
        nodes += inferred.junctions
        by_id.update({n.id: n for n in inferred.junctions})
        edges = inferred.edges
        self.stats["line_end_methods"] = inferred.end_methods
        self.stats["tap_substations_inserted"] = inferred.tap_substations_inserted

        edges += self._reconcile_cen_sections(b, nodes, by_id, edges)
        edges += self._sites(nodes)
        model_buses, model_branches = self._electrical(b, nodes, by_id, edges)
        plants = self._plants(b, nodes, by_id, model_buses)
        storage = self._storage(b, nodes, by_id, model_buses)
        self._graph_stats(nodes, edges)
        for p in plants:
            if p.operating and p.node in by_id:
                by_id[p.node].generation_mw += p.mw
        for s in storage:
            if s.node in by_id and s.mw and (s.build_year or 0) <= self.cfg.current_year:
                by_id[s.node].storage_mw += s.mw
        comunas, geometry = self._service_areas(b, nodes)
        zones = self._macro_zones(nodes, comunas, plants)
        for e in edges:
            if e.coords and len(e.coords) > 2:
                e.coords = simplify(e.coords, self.cfg.simplify_m)
            elif e.coords:
                e.coords = [(round(x, 5), round(y, 5)) for x, y in e.coords]

        self.stats.update(self._summary(nodes, edges, plants, storage, comunas))
        return GridSnapshot(
            version=SNAPSHOT_VERSION,
            built_at=datetime.now(UTC).isoformat(timespec="seconds"),
            sources=b.sources,
            nodes=nodes,
            edges=edges,
            plants=plants,
            storage=storage,
            comunas=comunas,
            macro_zones=zones,
            model_buses=model_buses,
            model_branches=model_branches,
            stats=self.stats,
            assumptions=self.assumptions,
            comuna_geometry=geometry,
        )

    # ------------------------------------------------------------ substations

    def _substations(self, b: SourceBundle) -> list[Node]:
        cen_by_id = {s.cen_id: s for s in b.cen_substations if s.cen_id is not None}
        kv_levels: dict[int, set[float]] = defaultdict(set)
        for bb in b.busbars:
            if bb.kv and bb.kv >= 1:
                kv_levels[bb.substation_cen_id].add(bb.kv)
        nodes: list[Node] = []
        seen_cen: set[int] = set()
        relabeled = 0
        for s in b.substations:
            if s.region_code in MEDIUM_SYSTEM_BY_REGION and (s.system or "SEN") == "SEN":
                s.system = MEDIUM_SYSTEM_BY_REGION[s.region_code]  # SEN ends in Los Lagos
                relabeled += 1
            cen = cen_by_id.get(s.cen_id) if s.cen_id is not None else None
            nid = (
                f"SE{s.cen_id}" if s.cen_id is not None and s.cen_id not in seen_cen else f"SEX{s.record_id}"
            )
            if s.cen_id is not None:
                seen_cen.add(s.cen_id)
            levels = sorted(kv_levels.get(s.cen_id or -1, set()) | ({s.kv} if s.kv else set()), reverse=True)
            prov = [Provenance(s.source, s.record_id, "ubicación, tensión, segmento, propietario, comuna")]
            ids: dict[str, Any] = {"ide_objectid": s.record_id}
            if cen:
                ids |= {"cen_id": cen.cen_id, "cen_code": cen.cen_code, "cen_name": cen.name}
                ids |= {k: v for k, v in cen.extra.items() if k.startswith("flag_")}
                prov.append(Provenance(cen.source, str(cen.cen_id), "código CEN, barras", method="id"))
            nodes.append(
                Node(
                    id=nid,
                    kind=NodeKind.SUBSTATION,
                    name=s.name,
                    lon=s.lon,
                    lat=s.lat,
                    kv=s.kv or (levels[0] if levels else None),
                    kv_levels=levels,
                    segment=s.segment,
                    system=s.system,
                    owner=s.owner,
                    region_code=s.region_code,
                    comuna_code=s.comuna_code,
                    location_source="IDE Energía",
                    ids=ids,
                    provenance=prov,
                )
            )
        cen_only = 0
        for cen in b.cen_substations:
            if cen.cen_id in seen_cen:
                continue
            cen_only += 1
            levels = sorted(kv_levels.get(cen.cen_id or -1, set()), reverse=True)
            nodes.append(
                Node(
                    id=f"SE{cen.cen_id}",
                    kind=NodeKind.SUBSTATION,
                    name=cen.name,
                    lon=None,
                    lat=None,
                    kv=levels[0] if levels else None,
                    kv_levels=levels,
                    owner=cen.owner,
                    system="SEN",
                    ids={"cen_id": cen.cen_id, "cen_code": cen.cen_code, "cen_name": cen.name},
                    provenance=[Provenance(cen.source, str(cen.cen_id), "nombre, código, barras")],
                )
            )
        self.stats["substations_ide"] = len(b.substations)
        self.stats["substations_relabeled_medium_system"] = relabeled
        self.stats["substations_cen"] = len(b.cen_substations)
        self.stats["substations_joined_by_id"] = len(seen_cen & set(cen_by_id))
        self.stats["substations_cen_only"] = cen_only
        return nodes

    def _name_index(self, nodes: list[Node]) -> dict[str, list[Node]]:
        idx: dict[str, list[Node]] = defaultdict(list)
        for n in nodes:
            if n.kind == NodeKind.SUBSTATION:
                idx[norm(n.name)].append(n)
                if n.ids.get("cen_name"):
                    idx[norm(n.ids["cen_name"])].append(n)
        return idx

    def _match_bus(
        self, bus_name: str, lon: float | None, lat: float | None, idx, nodes
    ) -> tuple[Node | None, str]:
        base = norm(re.sub(r"_\d+(\.\d+)?(aux\w*)?$", "", bus_name))
        cands = [n for n in idx.get(base, []) if n.kind == NodeKind.SUBSTATION]
        if lon is not None and lat is not None:
            located = [n for n in cands if n.located]
            if located:
                best = min(located, key=lambda n: haversine_km(lon, lat, n.lon, n.lat))
                if haversine_km(lon, lat, best.lon, best.lat) <= self.cfg.bus_match_m / 1000:
                    return best, "nombre"
            near = [
                n
                for n in nodes
                if n.kind == NodeKind.SUBSTATION
                and n.located
                and abs(n.lat - lat) < 0.06
                and abs(n.lon - lon) < 0.08
                and haversine_km(lon, lat, n.lon, n.lat) <= self.cfg.bus_match_m / 1000
            ]
            scored = sorted(((similarity(norm(n.name), base), n) for n in near), key=lambda t: -t[0])
            if scored and scored[0][0] >= 0.75:
                return scored[0][1], "nombre aproximado + distancia"
        if len(cands) == 1:
            return cands[0], "nombre"
        return None, "sin match"

    def _locate_from_model(self, b: SourceBundle, nodes: list[Node]) -> None:
        idx = self._name_index(nodes)
        located = 0
        for bus in b.buses:
            base = norm(re.sub(r"_\d+(\.\d+)?(aux\w*)?$", "", bus.name))
            for n in idx.get(base, []):
                if not n.located and bus.lon is not None:
                    n.lon, n.lat = bus.lon, bus.lat
                    n.location_source = "PyPSA-CL (barra del mismo nombre)"
                    n.provenance.append(Provenance(bus.source, bus.name, "ubicación", method="nombre"))
                    located += 1
        self.stats["substations_located_from_model"] = located

    # ------------------------------------------------------- CEN reconciliation

    def _resolve_end(
        self, desc: str | None, kv: float | None, line_code: str | None, code_idx, name_idx
    ) -> tuple:
        d = (desc or "").strip()
        kind = d.split(":", 1)[0].strip().upper()
        body = d.split(":", 1)[1].strip() if ":" in d else d
        if kind.startswith("PA"):
            for code in reversed(SE_CODE_RE.findall(body)):
                if code in code_idx:
                    return ("node", code_idx[code], "código de paño")
            text = re.sub(r"/[A-Z0-9-]+$", "", body.strip())  # trailing bay code "/PA005L0089SE001L0089"
            text = re.sub(r"^PA\s+", "", text.strip())
            key = norm(bay_stripped(text))
            cands = name_idx.get(key, [])
            if len(cands) > 1 and kv:
                kv_ok = [n for n in cands if any(abs(k - kv) < 1 for k in n.kv_levels)]
                cands = kv_ok or cands
            if cands:
                return ("node", sorted(cands, key=lambda n: (not n.located, n.id))[0], "nombre de paño")
            return ("unresolved", key, "paño sin match")
        if kind.startswith("TAP"):
            return ("tap", f"{norm(body).removeprefix('TAP ').strip()}|{kv or ''}", "tap")
        if kind.startswith("PUNTO"):
            return ("point", f"{line_code}:{norm(body)}", "punto")
        return ("unresolved", norm(body), "formato desconocido")

    def _reconcile_cen_sections(
        self, b: SourceBundle, nodes: list[Node], by_id: dict, edges: list[Edge]
    ) -> list[Edge]:
        """Check the official CEN line sections against the inferred topology and add the ones it lacks.

        IDE Energía gives line geometry but no ends, so `infer_line_topology` guesses them. CEN Infotecnica
        gives the ends of each section by name but no geometry. For every section:

        - Both ends are resolved to nodes. An end that cannot be resolved counts as `unresolved_end`, and a
          section whose ends are the same node counts as `self_loop`. Both are skipped. A declared tap reuses a
          TAP substation of that name, else a new `TAP-<n>` node. A declared line point becomes a `PT-<n>`
          junction. New nodes have no coordinates until `_place_declared_taps`.
        - `confirmed_direct`: an inferred edge already joins the two nodes (voltage within 1 kV when both are
          known). The section is attached to it as `ids["cen_tramos"]`.
        - `confirmed_via_taps`: a path of at most 4 hops through taps, junctions and TAP-named substations joins
          them. The section is attached to every edge of the path.
        - Otherwise a straight edge `T<id>` is added, with no public geometry. When both ends have coordinates and
          they are farther apart than `max_line_km(kv)`, the section is counted as `rejected_implausible` and not
          added. When an end has no coordinates the edge is added without geometry or length.

        Appends the new TAP / PT nodes to `nodes` and `by_id`, returns only the added edges, and stores the
        counters in `stats["cen_sections"]`. `validate_snapshot` reads them for `cen_sections_confirmed`."""
        code_idx = {n.ids["cen_code"]: n for n in nodes if n.ids.get("cen_code")}
        name_idx = self._name_index(nodes)
        tap_subs: dict[str, list[Node]] = defaultdict(list)
        for n in nodes:
            if n.kind == NodeKind.SUBSTATION and is_tap_name(n.name):
                key = re.sub(r"\b(TAP|OFF)\b", " ", norm(n.name))
                tap_subs[re.sub(r"\s+", " ", key).strip()].append(n)

        g = nx.Graph()
        for e in edges:
            g.add_edge(e.source_node, e.target_node)
        edge_by_pair: dict[frozenset, list[Edge]] = defaultdict(list)
        for e in edges:
            edge_by_pair[frozenset((e.source_node, e.target_node))].append(e)

        def via_non_substations(a: str, c: str, max_hops: int = 4) -> list[str] | None:
            if a not in g or c not in g:
                return None
            sub = g.subgraph(
                [
                    n
                    for n in g.nodes
                    if n in (a, c) or by_id[n].kind != NodeKind.SUBSTATION or is_tap_name(by_id[n].name)
                ]
            )
            try:
                path = nx.shortest_path(sub, a, c)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return None
            return path if len(path) - 1 <= max_hops else None

        tap_nodes: dict[str, Node] = {}
        point_nodes: dict[str, Node] = {}
        added: list[Edge] = []
        counters: Counter = Counter()
        for t in b.cen_sections:
            kv = t.kv or parse_kv(t.name)
            ends = [
                self._resolve_end(t.end1, kv, t.line_code, code_idx, name_idx),
                self._resolve_end(t.end2, kv, t.line_code, code_idx, name_idx),
            ]
            ids: list[str | None] = []
            for kind, ref, _method in ends:
                if kind == "node":
                    ids.append(ref.id)
                elif kind == "tap":
                    subs = tap_subs.get(ref.split("|", 1)[0]) or []
                    if subs:
                        ids.append(subs[0].id)
                        continue
                    if ref not in tap_nodes:
                        tap_nodes[ref] = Node(
                            id=f"TAP-{len(tap_nodes) + 1}",
                            kind=NodeKind.TAP,
                            name=f"TAP {ref.split('|', 1)[0]}",
                            lon=None,
                            lat=None,
                            kv=kv,
                            provenance=[Provenance(t.source, t.record_id, "derivación declarada en tramo")],
                        )
                        by_id[tap_nodes[ref].id] = tap_nodes[ref]
                    ids.append(tap_nodes[ref].id)
                elif kind == "point":
                    if ref not in point_nodes:
                        point_nodes[ref] = Node(
                            id=f"PT-{len(point_nodes) + 1}",
                            kind=NodeKind.JUNCTION,
                            name=f"punto {ref.split(':', 1)[1]}",
                            lon=None,
                            lat=None,
                            kv=kv,
                            provenance=[
                                Provenance(t.source, t.record_id, "punto de línea declarado en tramo")
                            ],
                        )
                        by_id[point_nodes[ref].id] = point_nodes[ref]
                    ids.append(point_nodes[ref].id)
                else:
                    ids.append(None)
            counters["sections"] += 1
            if None in ids:
                counters["unresolved_end"] += 1
                continue
            a, c = cast("list[str]", ids)  # no None: unresolved ends were skipped above
            if a == c:
                counters["self_loop"] += 1
                continue
            meta = {
                "cen_tramo_id": t.record_id,
                "cen_tramo": t.name,
                "circuit": t.circuit,
                "owner": t.owner,
                "cen_line": (b.cen_lines.get(t.line_code or "") or {}).get("nombre"),
            }
            direct = [
                e for e in edge_by_pair.get(frozenset((a, c)), []) if not kv or not e.kv or abs(e.kv - kv) < 1
            ]
            if direct:
                for e in direct:
                    e.ids.setdefault("cen_tramos", []).append(meta)
                counters["confirmed_direct"] += 1
                continue
            path = via_non_substations(a, c)
            if path:
                for u, v in itertools.pairwise(path):
                    for e in edge_by_pair.get(frozenset((u, v)), []):
                        e.ids.setdefault("cen_tramos", []).append(meta)
                counters["confirmed_via_taps"] += 1
                continue
            na, nc = by_id[a], by_id[c]
            coords = None
            geom = None
            if na.located and nc.located:
                dist = haversine_km(na.lon, na.lat, nc.lon, nc.lat)
                if dist > max_line_km(kv):
                    counters["rejected_implausible"] += 1
                    continue
                coords, geom = [(na.lon, na.lat), (nc.lon, nc.lat)], "recta esquemática (sin trazado público)"
            counters["added_from_cen"] += 1
            e = Edge(
                id=f"T{t.record_id}",
                kind=EdgeKind.LINE,
                name=t.name,
                source_node=a,
                target_node=c,
                kv=kv,
                circuit=t.circuit,
                owner=t.owner,
                system="SEN",
                length_km=round(haversine_km(na.lon, na.lat, nc.lon, nc.lat), 3) if coords else None,
                topology_source="CEN Infotecnica (tramo oficial)",
                geometry_source=geom,
                coords=coords,
                ids={"cen_tramos": [meta]},
                provenance=[
                    Provenance(
                        t.source, t.record_id, "extremos, tensión, circuito, propietario", method="tramo"
                    ),
                    Provenance(
                        "derived", None, "longitud", method="distancia en línea recta", is_assumption=True
                    ),
                ],
            )
            added.append(e)
            g.add_edge(a, c)
            edge_by_pair[frozenset((a, c))].append(e)
        new_nodes = list(tap_nodes.values()) + list(point_nodes.values())
        self._place_declared_taps(new_nodes, added, by_id)
        nodes += new_nodes
        self.stats["cen_sections"] = dict(counters)
        self.assumptions.append(
            "Tramos oficiales del CEN sin trazado en IDE Energía se dibujan como rectas esquemáticas entre sus "
            "subestaciones; su longitud es la distancia en línea recta."
        )
        return added

    def _place_declared_taps(self, new_nodes: list[Node], added: list[Edge], by_id: dict) -> None:
        """A declared tap with located neighbours goes on the straight segment between the two nearest."""
        nbrs: dict[str, list[str]] = defaultdict(list)
        for e in added:
            nbrs[e.source_node].append(e.target_node)
            nbrs[e.target_node].append(e.source_node)
        placed = 0
        for n in new_nodes:
            pts = [by_id[m] for m in nbrs.get(n.id, []) if m in by_id and by_id[m].located]
            if len(pts) >= 2:
                n.lon = round(float(np.mean([p.lon for p in pts])), 6)
                n.lat = round(float(np.mean([p.lat for p in pts])), 6)
            elif len(pts) == 1:
                n.lon, n.lat = pts[0].lon, pts[0].lat
            else:
                continue
            n.location_source = "aproximada: promedio de sus vecinos"
            n.provenance.append(
                Provenance("derived", None, "ubicación", method="promedio de vecinos", is_assumption=True)
            )
            placed += 1
        for e in added:
            a, c = by_id[e.source_node], by_id[e.target_node]
            if e.coords is None and a.located and c.located:
                e.coords = [(a.lon, a.lat), (c.lon, c.lat)]
                e.geometry_source = "recta esquemática (sin trazado público)"
                e.length_km = round(haversine_km(a.lon, a.lat, c.lon, c.lat), 3)
        self.stats["declared_taps_placed"] = placed

    # ------------------------------------------------------------------ sites

    def _sites(self, nodes: list[Node]) -> list[Edge]:
        subs = [n for n in nodes if n.kind == NodeKind.SUBSTATION and n.located]
        xy = project(np.array([n.lon for n in subs]), np.array([n.lat for n in subs]))
        g = nx.Graph()
        g.add_nodes_from(range(len(subs)))
        for j in range(len(subs)):
            d = np.hypot(*(xy - xy[j]).T)
            for k in np.where((d <= self.cfg.site_m) & (np.arange(len(d)) > j))[0]:
                g.add_edge(j, int(k))
        out: list[Edge] = []
        for s, comp in enumerate(sorted(nx.connected_components(g), key=min), start=1):
            comp = sorted(comp)
            for j in comp:
                subs[j].site = f"SITE{s}"
            if len(comp) < 2:
                continue
            hub = max(comp, key=lambda j: (subs[j].kv or 0, len(subs[j].kv_levels), -len(subs[j].name)))
            for j in comp:
                if j == hub:
                    continue
                a, c = subs[hub], subs[j]
                out.append(
                    Edge(
                        id=f"B-{a.id}-{c.id}",
                        kind=EdgeKind.COLOCATED,
                        name=f"acople {a.name} / {c.name}",
                        source_node=a.id,
                        target_node=c.id,
                        length_km=round(haversine_km(a.lon, a.lat, c.lon, c.lat), 3),
                        topology_source="supuesto de acople",
                        geometry_source="recta",
                        coords=[(a.lon, a.lat), (c.lon, c.lat)],
                        is_assumption=True,
                        provenance=[
                            Provenance(
                                "derived",
                                None,
                                "conexión",
                                method=f"distancia < {self.cfg.site_m:.0f} m",
                                is_assumption=True,
                            )
                        ],
                    )
                )
        for n in nodes:
            n.site = n.site or n.id
        self.assumptions.append(
            f"Subestaciones a menos de {self.cfg.site_m:.0f} m se consideran un mismo sitio, unidas por un acople "
            "(la capa pública no incluye las barras ni los acoplamientos internos)."
        )
        return out

    # -------------------------------------------------------------- electrical

    def _electrical(self, b: SourceBundle, nodes: list[Node], by_id: dict, edges: list[Edge]):
        """Match PyPSA-CL buses to substations and attach the model's branch parameters to the lines.

        Buses are matched by `_match_bus`, which records the method. A branch is attached when both its end buses
        map to different nodes, and the inferred LINE edges between the same two sites (not nodes, so a bus of
        another voltage in the same substation still matches) have a voltage within 1 kV of the branch. Branches
        built after `cfg.current_year` are not attached. Each matching edge gets the whole corridor's r, x and
        s_nom, so with n parallel edges each one reports the corridor value, not one circuit's. `validate_snapshot`
        accounts for that in its reactance check. Returns the model buses and the branches."""
        idx = self._name_index(nodes)
        subs = [n for n in nodes if n.kind == NodeKind.SUBSTATION]
        buses: dict[str, ModelBus] = {}
        for bus in b.buses:
            node, method = self._match_bus(bus.name, bus.lon, bus.lat, idx, subs)
            buses[bus.name] = ModelBus(bus.name, bus.kv, bus.lon, bus.lat, node.id if node else None, method)
            if node:
                node.ids.setdefault("model_buses", []).append(bus.name)
        site_of = {n.id: n.site for n in nodes}
        edges_by_site_pair: dict[frozenset, list[Edge]] = defaultdict(list)
        for e in edges:
            if e.kind == EdgeKind.LINE:
                edges_by_site_pair[
                    frozenset((site_of.get(e.source_node), site_of.get(e.target_node)))
                ].append(e)
        branches: list[ModelBranch] = []
        attached = 0
        for br in b.branches:
            n0 = self._bus_node(br.bus0, buses, idx, subs)
            n1 = self._bus_node(br.bus1, buses, idx, subs)
            mb = ModelBranch(
                br.name,
                br.bus0,
                br.bus1,
                n0,
                n1,
                br.kv,
                br.s_nom_mva,
                br.r_ohm,
                br.x_ohm,
                br.r_pu,
                br.x_pu,
                br.build_year,
                br.asset_type,
            )
            if n0 and n1 and n0 != n1:
                pair = frozenset((site_of.get(n0), site_of.get(n1)))
                match = [
                    e
                    for e in edges_by_site_pair.get(pair, [])
                    if not br.kv or not e.kv or abs(e.kv - br.kv) < 1
                ]
                if match and (br.build_year or 0) <= self.cfg.current_year:
                    n_par = len(match)
                    for e in match:
                        e.electrical = ElectricalParams(
                            r_ohm=br.r_ohm,
                            x_ohm=br.x_ohm,
                            s_nom_mva=br.s_nom_mva,
                            source="pypsa_cl",
                            branch=br.name,
                            note=f"parámetros del corredor PyPSA-CL ({n_par} tramo(s) en el corredor)",
                        )
                        e.provenance.append(
                            Provenance("pypsa_cl", br.name, "r, x, s_nom", method="corredor por sitios")
                        )
                    mb.edges = [e.id for e in match]
                    attached += 1
            branches.append(mb)
        self.stats["model_buses"] = len(buses)
        self.stats["model_buses_matched"] = sum(1 for x in buses.values() if x.node)
        self.stats["model_branches"] = len(branches)
        self.stats["model_branches_attached"] = attached
        self.assumptions.append(
            "Reactancias y capacidades vienen del modelo reducido PyPSA-CL (Ministerio de Energía); se asignan a los "
            "tramos que unen los mismos sitios y la misma tensión, por lo que representan el corredor completo."
        )
        return list(buses.values()), branches

    def _bus_node(self, bus_name: str, buses: dict[str, ModelBus], idx, subs) -> str | None:
        if bus_name in buses and buses[bus_name].node:
            return buses[bus_name].node
        base = re.sub(r"(aux\w*)$", "", bus_name)
        if base in buses and buses[base].node:
            return buses[base].node
        node, _ = self._match_bus(bus_name, None, None, idx, subs)
        return node.id if node else None

    # ------------------------------------------------------------------ plants

    def _plants(self, b: SourceBundle, nodes: list[Node], by_id: dict, buses: list[ModelBus]) -> list[Plant]:
        """Connect every IDE plant to a node and record how in `connection_method`. The first strategy that finds
        a node wins:

        1. PyPSA-CL generator: model generators within `model_gen_m` (3 km) with a compatible technology. The
           one whose name is most similar picks the connection bus, and that bus maps to a node. All units on
           that bus within range go to `model_units`, and the mean of their inertia constants becomes `inertia_s`.
           If the bus has no node, the plant falls through to the next strategy.
        2. Name: a substation within `plant_name_m` (25 km) whose name contains the plant name as whole words, or
           is similar to it (`name_ok`) once "CENTRAL " is removed. Whole-word matches come first, then
           substations of the main component (`component == 0`), then the nearest.
        3. Nearest substation, with no distance limit. Only this method is marked `is_assumption` in the
           provenance.

        Plants without coordinates are skipped. Duplicates by name and rounded position keep the first. The CEN
        plant with the same `plant_key` gives `cen_id` and `cen_name`. Counts per method are stored in
        `stats["plant_connection_methods"]`."""
        subs = [n for n in nodes if n.kind == NodeKind.SUBSTATION and n.located]
        sindex = PointIndex([cast(float, n.lon) for n in subs], [cast(float, n.lat) for n in subs])
        sub_names = [norm(n.name) for n in subs]
        bus_node = {x.name: x.node for x in buses}
        gens = [g for g in b.model_generators if g.lon is not None]
        gindex = (
            PointIndex([cast(float, g.lon) for g in gens], [cast(float, g.lat) for g in gens])
            if gens
            else None
        )
        cen_by_key: dict[str, list[RawPlant]] = defaultdict(list)
        for c in b.cen_plants:
            cen_by_key[plant_key(c.name)].append(c)

        out: list[Plant] = []
        methods: Counter = Counter()
        seen: set = set()
        for p in b.plants:
            if p.lon is None or p.lat is None:
                continue
            key = (p.name, round(p.lon, 4), round(p.lat, 4))
            if key in seen:
                continue
            seen.add(key)
            prov = [Provenance(p.source, p.record_id, "ubicación, potencia, tecnología, estado")]
            node_id, method, dist = None, "sin asignar", None
            units: list[str] = []
            inertia = None
            if gindex is not None:
                near = gindex.within(p.lon, p.lat, self.cfg.model_gen_m)
                near = [(i, d) for i, d in near if tech_compatible(p.tech, gens[i].tech)]
                if near:
                    best_name = max(
                        near, key=lambda t: (similarity(plant_key(gens[t[0]].name), plant_key(p.name)), -t[1])
                    )
                    sel = [i for i, _ in near if gens[i].connection_bus == gens[best_name[0]].connection_bus]
                    bus = gens[best_name[0]].connection_bus
                    if bus and bus_node.get(bus):
                        node_id, method, dist = bus_node[bus], "barra declarada en PyPSA-CL", None
                        units = [gens[i].name for i in sel]
                        h = [cast(float, gens[i].inertia_s) for i in sel if gens[i].inertia_s]
                        inertia = round(float(np.mean(h)), 3) if h else None
                        prov.append(
                            Provenance(
                                "pypsa_cl",
                                gens[best_name[0]].record_id,
                                "barra de conexión",
                                method="unidad a < 3 km",
                            )
                        )
            if node_id is None:
                d = sindex.distances(p.lon, p.lat)
                target = norm(p.name)
                pat = re.compile(rf"\b{re.escape(target)}\b") if target else None
                cand = [
                    j
                    for j in np.where(d <= self.cfg.plant_name_m)[0]
                    if pat
                    and (
                        cast(re.Pattern[str], pat).search(sub_names[j])
                        or similarity(sub_names[j].removeprefix("CENTRAL ").strip(), target)
                        >= self.cfg.name_ok
                    )
                ]
                if cand:
                    j = min(
                        cand,
                        key=lambda k: (
                            not cast(re.Pattern[str], pat).search(sub_names[k]),
                            subs[k].component != 0,
                            d[k],
                        ),
                    )
                    node_id, method, dist = subs[j].id, "nombre de subestación", float(d[j]) / 1000
                else:
                    nearest = int(np.argmin(d))
                    node_id, method, dist = (
                        subs[nearest].id,
                        "subestación más cercana",
                        float(d[nearest]) / 1000,
                    )
                prov.append(
                    Provenance(
                        "derived",
                        None,
                        "nodo de conexión",
                        method=method,
                        is_assumption=method != "nombre de subestación",
                    )
                )
            methods[method] += 1
            cen = None
            for c in cen_by_key.get(plant_key(p.name), []):
                cen = c
                break
            if cen:
                prov.append(Provenance(cen.source, cen.record_id, "nombre y código CEN", method="nombre"))
            out.append(
                Plant(
                    id=f"P{p.record_id}",
                    name=p.name,
                    tech=p.tech or "otra",
                    mw=round(p.mw or 0.0, 3),
                    lon=round(p.lon, 6),
                    lat=round(p.lat, 6),
                    node=node_id,
                    connection_method=method,
                    connection_distance_km=round(dist, 2) if dist is not None else None,
                    status=p.status,
                    operating=p.operating,
                    system=p.system,
                    owner=p.owner,
                    fuel=p.fuel,
                    region_code=p.region_code,
                    comuna_code=p.comuna_code,
                    cen_id=int(cen.record_id) if cen else None,
                    cen_name=cen.name if cen else None,
                    inertia_s=inertia,
                    model_units=units,
                    provenance=prov,
                )
            )
        self.stats["plant_connection_methods"] = dict(methods)
        self.stats["plants_with_cen_id"] = sum(1 for p in out if p.cen_id)
        return out

    def _storage(
        self, b: SourceBundle, nodes: list[Node], by_id: dict, buses: list[ModelBus]
    ) -> list[Storage]:
        idx = self._name_index(nodes)
        subs = [n for n in nodes if n.kind == NodeKind.SUBSTATION and n.located]
        sindex = PointIndex([cast(float, n.lon) for n in subs], [cast(float, n.lat) for n in subs])
        bus_node = {x.name: x.node for x in buses}
        out: list[Storage] = []
        for s in b.storage:
            node, method = None, "subestación más cercana"
            cands = idx.get(norm(s.substation_name), [])
            if cands:
                node, method = cands[0], "subestación declarada"
            elif s.lon is not None:
                node = subs[int(np.argmin(sindex.distances(s.lon, cast(float, s.lat))))]
            out.append(
                Storage(
                    f"BESS{s.record_id}",
                    s.name,
                    s.lon,
                    s.lat,
                    node.id if node else None,
                    method,
                    s.mw,
                    s.hours,
                    s.equipment,
                    s.owner,
                    s.build_year,
                    s.source,
                    [Provenance(s.source, s.record_id, "inventario", method=method)],
                )
            )
        for s in b.model_storage:
            nid = bus_node.get(s.connection_bus or "")
            n = by_id.get(nid) if nid else None
            out.append(
                Storage(
                    f"MS-{s.record_id}",
                    s.name,
                    n.lon if n else None,
                    n.lat if n else None,
                    nid,
                    "barra declarada en PyPSA-CL",
                    s.mw,
                    s.hours,
                    s.equipment,
                    s.owner,
                    s.build_year,
                    s.source,
                    [Provenance(s.source, s.record_id, "potencia, horas, año", method="barra declarada")],
                )
            )
        return out

    # ----------------------------------------------------------- graph stats

    def _graph_stats(self, nodes: list[Node], edges: list[Edge]) -> None:
        g = nx.MultiGraph()
        g.add_nodes_from(n.id for n in nodes)
        for e in edges:
            g.add_edge(e.source_node, e.target_node, key=e.id)
        comps = sorted(nx.connected_components(g), key=len, reverse=True)
        comp_of = {n: k for k, c in enumerate(comps) for n in c}
        for n in nodes:
            n.component = comp_of.get(n.id, -1)
            n.degree = g.degree(n.id)
            n.macro_zone = REGION_TO_MACRO.get(n.region_code or "")
        self.stats["components"] = len(comps)
        self.stats["largest_component_nodes"] = len(comps[0]) if comps else 0
        self.stats["component_sizes_top10"] = [len(c) for c in comps[:10]]
        self.stats["isolated_nodes"] = sum(1 for c in comps if len(c) == 1)

    # ------------------------------------------------------------ service areas

    def _is_delivery(self, n: Node) -> bool:
        if n.kind != NodeKind.SUBSTATION or not n.located:
            return False
        up = ascii_upper(n.name)
        if re.search(r"\bCENTRAL\b|\bTAP\b|SECCIONADORA|\bPARQUE\b|\bPFV\b|\bSOLAR\b|\bEOLIC", up):
            return False
        if n.system and n.system != "SEN":
            return True
        if n.component != 0:
            return False
        if n.segment == "ZONAL":
            return True
        return n.segment == "NACIONAL" and (n.kv or 0) <= 220

    def _service_areas(self, b: SourceBundle, nodes: list[Node]):
        delivery = [n for n in nodes if self._is_delivery(n)]
        for n in delivery:
            n.delivers = True
        geometry = {c.cut: c.geometry for c in b.comunas if c.geometry}
        if not delivery or not b.comunas:
            return [], geometry
        dindex = PointIndex([cast(float, n.lon) for n in delivery], [cast(float, n.lat) for n in delivery])
        per_comuna: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        urban_by_comuna: dict[str, float] = defaultdict(float)
        for z in b.census_zones:
            j = int(np.argmin(dindex.distances(z.lon, z.lat)))
            per_comuna[z.cut][delivery[j].id] += z.population
            urban_by_comuna[z.cut] += z.population
        by_comuna_nodes: dict[str, list[Node]] = defaultdict(list)
        for n in delivery:
            if n.comuna_code:
                by_comuna_nodes[str(int(n.comuna_code))].append(n)
        comunas: list[Comuna] = []
        for c in b.comunas:
            rural = max(0.0, c.population - urban_by_comuna.get(c.cut, 0.0))
            if rural > 0:
                inside = by_comuna_nodes.get(c.cut, [])
                if inside:
                    for n in inside:
                        per_comuna[c.cut][n.id] += rural / len(inside)
                elif c.centroid:
                    j = int(np.argmin(dindex.distances(*c.centroid)))
                    per_comuna[c.cut][delivery[j].id] += rural
            total = sum(per_comuna[c.cut].values()) or 1.0
            hh = c.households or 0
            shares = [
                ServiceShare(nid, round(pop, 1), round(hh * pop / total, 1), round(pop / total, 4))
                for nid, pop in sorted(per_comuna[c.cut].items(), key=lambda t: -t[1])
            ]
            comunas.append(
                Comuna(
                    c.cut,
                    c.name,
                    c.region_code,
                    c.region_name,
                    c.province_name,
                    c.population,
                    c.households,
                    c.dwellings,
                    c.centroid,
                    REGION_TO_MACRO.get(c.region_code),
                    shares,
                )
            )
        node_by_id = {n.id: n for n in nodes}
        for comuna in comunas:
            for s in comuna.served_by:
                node_by_id[s.node].served_population += s.population
                node_by_id[s.node].served_households += s.households
        self.stats["delivery_substations"] = len(delivery)
        self.stats["population_assigned"] = round(sum(n.served_population for n in nodes))
        self.stats["population_census"] = sum(c.population for c in b.comunas)
        self.assumptions.append(
            "Zonas abastecidas: cada zona censal urbana (INE Censo 2024) se asigna a la subestación de entrega más "
            "cercana (zonal, o nacional de 220 kV o menos, excluyendo centrales, taps y seccionadoras); la población "
            "rural restante de cada comuna se reparte entre las subestaciones de entrega ubicadas en ella, o va a la "
            "más cercana a su centroide. Es una aproximación geográfica, no el mapa real de alimentadores."
        )
        self.assumptions.append(
            "Zonas eléctricas (Norte Grande, Norte Chico, Centro, Centro-Sur, Sur, Aysén, Magallanes) definidas por "
            "región administrativa."
        )
        return comunas, geometry

    def _macro_zones(self, nodes: list[Node], comunas: list[Comuna], plants: list[Plant]) -> list[MacroZone]:
        zones = {z.id: MacroZone(z.id, z.name, list(z.region_codes), z.color) for z in MACRO_ZONES}
        for c in comunas:
            if c.macro_zone in zones:
                zones[c.macro_zone].population += c.population
        for n in nodes:
            if n.macro_zone in zones and n.kind == NodeKind.SUBSTATION:
                zones[n.macro_zone].substations += 1
        for p in plants:
            z = REGION_TO_MACRO.get(p.region_code or "")
            if z in zones and p.operating:
                zones[z].generation_mw += p.mw
        for zone in zones.values():
            zone.generation_mw = round(zone.generation_mw, 1)
        return list(zones.values())

    # ---------------------------------------------------------------- summary

    def _summary(self, nodes, edges, plants, storage, comunas) -> dict:
        lines = [e for e in edges if e.kind == EdgeKind.LINE]
        return {
            "nodes": len(nodes),
            "nodes_by_kind": dict(Counter(n.kind.value for n in nodes)),
            "nodes_located": sum(1 for n in nodes if n.located),
            "edges": len(edges),
            "line_edges": len(lines),
            "line_edges_with_cen_tramo": sum(1 for e in lines if e.ids.get("cen_tramos")),
            "line_edges_with_electrical": sum(1 for e in lines if e.electrical),
            "line_edges_by_topology_source": dict(Counter(e.topology_source for e in lines)),
            "line_km": round(sum(e.length_km or 0 for e in lines)),
            "plants": len(plants),
            "plants_operating_sen": sum(1 for p in plants if p.operating and p.system == "SEN"),
            "mw_operating_sen": round(sum(p.mw for p in plants if p.operating and p.system == "SEN"), 1),
            "storage_records": len(storage),
            "comunas": len(comunas),
        }


def max_line_km(kv: float | None) -> float:
    """Longest plausible straight distance for a single section at this voltage."""
    if not kv:
        return 150.0
    if kv <= 70:
        return 80.0
    if kv <= 160:
        return 150.0
    if kv <= 230:
        return 300.0
    return 450.0


def plant_key(name: str | None) -> str:
    n = norm(name)
    n = PLANT_PREFIX_RE.sub("", n)
    n = re.sub(r"\b(U|UNIDAD|TG|TV|CC)\s*\d+[A-Z]?\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


TECH_GROUPS = {
    "solar": {"solar", "solar_pv", "csp", "pv", "solar fotovoltaica"},
    "eolica": {"eolica", "onshore wind", "offshore wind", "wind"},
    "hidro": {"hidro", "hydro reservoir", "hydro ror", "hydro", "pumped hydro"},
    "termica": {"termica", "diesel", "coal", "gas", "lng", "fuel oil", "biomass", "cogeneration"},
    "bioenergia": {"bioenergia", "biomass", "biogas"},
    "geotermica": {"geotermica", "geothermal"},
}


def tech_compatible(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return True
    b_low = b.lower()
    group = TECH_GROUPS.get(a, {a})
    return any(t in b_low for t in group) or b_low in group
