"""Infer line end points from geometry (the IDE line layer has no from/to fields).

Rules, in order, for each end of each line part:
1. A substation within `snap_m` whose name matches one end of the line name wins.
2. Otherwise the nearest substation within snap_m / 3.
3. Otherwise a substation whose name matches, within `name_snap_m`.
4. Otherwise the nearest substation within snap_m.
Ends still unmatched that touch another line's interior are taps: the host line is split and a
junction node is created. Substations named TAP / SECCIONADORA that sit next to a line of their
voltage (and are not already attached at two ends) split that line too. Remaining ends join a
nearby end, cluster into a junction, or become dangling nodes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from cascadasen.domain.geo import interpolate, project, seg_distance, slice_line
from cascadasen.domain.model import Edge, EdgeKind, Node, NodeKind, Provenance, RawLine
from cascadasen.domain.naming import is_tap_name, line_ends, name_score


@dataclass(frozen=True)
class InferenceConfig:
    snap_m: float = 1500.0
    name_snap_m: float = 10000.0
    tap_m: float = 150.0
    junction_m: float = 150.0
    tap_sub_m: float = 2000.0
    name_ok: float = 0.82


@dataclass
class _Part:
    line: RawLine
    part: int
    ll: np.ndarray
    xy: np.ndarray
    tokens: list[str]


@dataclass
class InferenceResult:
    junctions: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    end_methods: dict[str, int] = field(default_factory=dict)
    tap_substations_inserted: int = 0


def infer_line_topology(
    substations: list[Node], lines: list[RawLine], cfg: InferenceConfig | None = None
) -> InferenceResult:
    cfg = cfg or InferenceConfig()
    subs = [n for n in substations if n.located]
    sub_ll = np.array([(n.lon, n.lat) for n in subs], dtype=float)
    sub_xy = project(sub_ll[:, 0], sub_ll[:, 1])

    parts: list[_Part] = []
    for ln in lines:
        if not ln.coords or len(ln.coords) < 2:
            continue
        seqs = ln.extra.get("parts") or [ln.coords]
        for k, seq in enumerate(seqs):
            if len(seq) < 2:
                continue
            ll = np.asarray(seq, dtype=float)
            parts.append(_Part(ln, k, ll, project(ll[:, 0], ll[:, 1]), line_ends(ln.name)))

    ends: dict[tuple[int, int], dict] = {}
    for i, pt in enumerate(parts):
        for end in (0, 1):
            ends_xy = pt.xy[0 if end == 0 else -1]
            d = np.hypot(*(sub_xy - ends_xy).T)
            near = np.where(d <= cfg.name_snap_m)[0]
            near = near[np.argsort(d[near])]
            scored = [(name_score(subs[j].name, pt.tokens), j) for j in near]
            named = [(s, j) for s, j in scored if s >= cfg.name_ok]
            named_close = [(s, j) for s, j in named if d[j] <= cfg.snap_m]
            choice = None
            if named_close:
                _, j = max(named_close, key=lambda sj: (sj[0], -d[sj[1]]))
                choice = (j, "snap+name")
            elif len(near) and d[near[0]] <= cfg.snap_m / 3:
                choice = (int(near[0]), "snap")
            elif named:
                _, j = max(named, key=lambda sj: (sj[0], -d[sj[1]]))
                choice = (j, "name")
            elif len(near) and d[near[0]] <= cfg.snap_m:
                choice = (int(near[0]), "snap_far")
            if choice:
                j, method = choice
                ends[(i, end)] = {"node": subs[j].id, "method": method, "dist_m": round(float(d[j]))}

    # taps: unmatched ends touching another line's interior
    taps: dict[int, list] = defaultdict(list)
    still: list[tuple[int, int]] = []
    for i, end in [(i, e) for i in range(len(parts)) for e in (0, 1) if (i, e) not in ends]:
        p = parts[i].xy[0 if end == 0 else -1]
        best = _nearest_interior(parts, p, cfg.tap_m, exclude={i})
        if best and 1.0 < best[2] < best[3] - 1.0:
            taps[best[1]].append((best[2], (i, end)))
        else:
            still.append((i, end))

    result = InferenceResult()
    host_cuts: dict[int, list[tuple[float, str]]] = defaultdict(list)
    junction_count = 0
    for h, lst in taps.items():
        lst.sort()
        groups: list[list] = []
        for along, ie in lst:
            if groups and along - groups[-1][-1][0] <= cfg.junction_m:
                groups[-1].append((along, ie))
            else:
                groups.append([(along, ie)])
        for g in groups:
            along = float(np.mean([a for a, _ in g]))
            junction_count += 1
            jid = f"J{junction_count}"
            ll_pt = interpolate(parts[h].ll, along, parts[h].xy)
            result.junctions.append(
                _junction(jid, ll_pt, NodeKind.TAP, f"derivación en {parts[h].line.name}")
            )
            host_cuts[h].append((along, jid))
            for _, ie in g:
                ends[ie] = {"node": jid, "method": "tap", "dist_m": 0}

    # tap / sectioning substations next to a line the layer does not cut there
    attached: dict[str, int] = defaultdict(int)
    for v in ends.values():
        attached[v["node"]] += 1
    for j, n in enumerate(subs):
        if not is_tap_name(n.name) or attached[n.id] >= 2:
            continue
        best = None
        for h, host in enumerate(parts):
            if n.id in (ends.get((h, 0), {}).get("node"), ends.get((h, 1), {}).get("node")):
                continue
            if n.kv and host.line.kv and abs(host.line.kv - n.kv) > 1:
                continue
            cand = _nearest_interior([host], sub_xy[j], cfg.tap_sub_m, exclude=set(), margin=200)
            if cand and (best is None or cand[0] < best[0]):
                best = (cand[0], h, cand[2])
        if best:
            host_cuts[best[1]].append((best[2], n.id))
            result.tap_substations_inserted += 1

    # remaining ends: join an existing end nearby, else cluster, else dangling
    end_xy = {(i, e): parts[i].xy[0 if e == 0 else -1] for i in range(len(parts)) for e in (0, 1)}
    resolved = list(ends)
    resolved_xy = np.array([end_xy[k] for k in resolved]) if resolved else np.zeros((0, 2))
    pending = []
    for ie in still:
        d = np.hypot(*(resolved_xy - end_xy[ie]).T) if len(resolved_xy) else np.array([])
        if len(d) and d.min() <= cfg.junction_m:
            nearest = resolved[int(np.argmin(d))]
            ends[ie] = {"node": ends[nearest]["node"], "method": "join_end", "dist_m": round(float(d.min()))}
        else:
            pending.append(ie)
    clusters: list[list] = []
    for ie in pending:
        for c in clusters:
            if any(np.hypot(*(end_xy[o] - end_xy[ie])) <= cfg.junction_m for o in c):
                c.append(ie)
                break
        else:
            clusters.append([ie])
    dangling = 0
    for c in clusters:
        i, e = c[0]
        ll_pt = parts[i].ll[0 if e == 0 else -1]
        if len(c) > 1:
            junction_count += 1
            nid, kind, note, method = f"J{junction_count}", NodeKind.JUNCTION, "unión de líneas", "junction"
        else:
            dangling += 1
            nid, kind, note, method = f"X{dangling}", NodeKind.DANGLING, "extremo sin S/E", "dangling"
        result.junctions.append(_junction(nid, ll_pt, kind, note))
        for ie in c:
            ends[ie] = {"node": nid, "method": method, "dist_m": 0}

    # edges (split hosts at taps)
    methods: dict[str, int] = defaultdict(int)
    for i, pt in enumerate(parts):
        ln = pt.line
        a, b = ends[(i, 0)], ends[(i, 1)]
        total = float(np.hypot(*np.diff(pt.xy, axis=0).T).sum())
        cuts = sorted(host_cuts.get(i, []))
        stops = [
            (0.0, a["node"], a["method"]),
            *[(al, nid, "tap" if nid.startswith("J") else "tap_substation") for al, nid in cuts],
            (total, b["node"], b["method"]),
        ]
        for k in range(len(stops) - 1):
            s0, s1 = stops[k], stops[k + 1]
            methods[s0[2]] += 1
            methods[s1[2]] += 1
            piece = slice_line(pt.ll, pt.xy, s0[0], s1[0])
            frac = (s1[0] - s0[0]) / total if total else 1.0
            eid = (
                f"L{ln.record_id}"
                + (f"p{pt.part}" if pt.part else "")
                + (f"s{k + 1}" if len(stops) > 2 else "")
            )
            result.edges.append(
                Edge(
                    id=eid,
                    kind=EdgeKind.LINE,
                    name=ln.name,
                    source_node=s0[1],
                    target_node=s1[1],
                    kv=ln.kv,
                    circuit=ln.circuit,
                    segment=ln.segment,
                    system=ln.system,
                    owner=ln.owner,
                    length_km=round((ln.length_km or total / 1000) * frac, 3),
                    topology_source="inferida (geometría + nombre)",
                    geometry_source="IDE Energía",
                    coords=[(float(x), float(y)) for x, y in piece],
                    ids={"ide_objectid": ln.record_id, "ide_tramo": ln.extra.get("tramo")},
                    provenance=[
                        Provenance(ln.source, ln.record_id, "geometría, tensión, longitud, segmento"),
                        Provenance(ln.source, ln.record_id, "extremos", method=f"{s0[2]}/{s1[2]}"),
                    ],
                )
            )
    result.end_methods = dict(methods)
    return result


def _nearest_interior(
    parts: list[_Part], p: np.ndarray, radius: float, exclude: set[int], margin: float = 0.0
):
    best = None
    for h, host in enumerate(parts):
        if h in exclude:
            continue
        xy = host.xy
        lo, hi = xy.min(0) - radius, xy.max(0) + radius
        if not (lo[0] <= p[0] <= hi[0] and lo[1] <= p[1] <= hi[1]):
            continue
        seglen = np.hypot(*np.diff(xy, axis=0).T)
        cum = np.r_[0, np.cumsum(seglen)]
        for s in range(len(xy) - 1):
            dist, t = seg_distance(p, xy[s], xy[s + 1])
            along = cum[s] + t * seglen[s]
            if dist <= radius and margin < along < cum[-1] - margin and (best is None or dist < best[0]):
                best = (dist, h, float(along), float(cum[-1]))
    return best


def _junction(nid: str, ll_pt, kind: NodeKind, note: str) -> Node:
    return Node(
        id=nid,
        kind=kind,
        name=note,
        lon=round(float(ll_pt[0]), 6),
        lat=round(float(ll_pt[1]), 6),
        location_source="geometría de líneas IDE",
        provenance=[Provenance("ide_energia", None, "ubicación", method="inferida", is_assumption=True)],
    )
