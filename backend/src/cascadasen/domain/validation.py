"""Data checks run on every build. Each check returns ok / warn / fail with the measured value.

They cover four questions: does the data cover the whole country, is the grid connected end to
end, do the sources agree with each other, and are electrical values physically plausible.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

import networkx as nx

from cascadasen.domain.geo import haversine_km
from cascadasen.domain.model import EdgeKind, GridSnapshot, NodeKind
from cascadasen.domain.naming import line_ends, name_score

CHILE_BBOX = (-76.0, -56.5, -66.0, -17.0)  # lon_min, lat_min, lon_max, lat_max
OFFICIAL_POPULATION_2024 = 18_480_432  # INE, primeros resultados Censo 2024
# 500 kV backbone corridors, north to south (CEN single-line diagram)
BACKBONE_500 = [
    ("KIMAL", "LOS CHANGOS"),
    ("LOS CHANGOS", "JADRESIC"),
    ("JADRESIC", "CUMBRE"),
    ("CUMBRE", "NUEVA CARDONES"),
    ("NUEVA CARDONES", "NUEVA MAITENCILLO"),
    ("NUEVA MAITENCILLO", "NUEVA PAN DE AZUCAR"),
    ("NUEVA PAN DE AZUCAR", "POLPAICO"),
    ("POLPAICO", "LO AGUIRRE"),
    ("LO AGUIRRE", "ALTO JAHUEL"),
    ("ALTO JAHUEL", "ANCOA"),
    ("ANCOA", "CHARRUA"),
]
# typical positive-sequence reactance of overhead lines, ohm/km (range per voltage class)
X_PER_KM = {
    500: (0.20, 0.45),
    345: (0.25, 0.50),
    220: (0.30, 0.55),
    154: (0.30, 0.60),
    110: (0.30, 0.65),
    66: (0.25, 0.70),
}


def _check(
    cid: str, title: str, status: str, value: Any, expected: str, detail: str = "", items: list | None = None
):
    out = {
        "id": cid,
        "title": title,
        "status": status,
        "value": value,
        "expected": expected,
        "detail": detail,
    }
    if items:
        out["items"] = items[:30]
    return out


def point_in_geometry(lon: float, lat: float, geom: dict) -> bool:
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for poly in polys:
        if _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, h) for h in poly[1:]):
            return True
    return False


def _in_ring(x: float, y: float, ring: list) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi + 1e-15) + xi:
            inside = not inside
        j = i
    return inside


def _bbox(geom: dict) -> tuple[float, float, float, float]:
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    xs = [c[0] for p in polys for c in p[0]]
    ys = [c[1] for p in polys for c in p[0]]
    return min(xs), min(ys), max(xs), max(ys)


def comuna_of_point(lon: float, lat: float, shapes: list[tuple[str, tuple, dict]]) -> str | None:
    for cut, bb, geom in shapes:
        if bb[0] <= lon <= bb[2] and bb[1] <= lat <= bb[3] and point_in_geometry(lon, lat, geom):
            return cut
    return None


def validate_snapshot(s: GridSnapshot) -> dict[str, Any]:
    checks: list[dict] = []
    nodes = {n.id: n for n in s.nodes}
    subs = [n for n in s.nodes if n.kind == NodeKind.SUBSTATION]
    sen_subs = [n for n in subs if (n.system or "SEN") == "SEN"]
    lines = [e for e in s.edges if e.kind == EdgeKind.LINE]

    # ---------- coverage ----------
    located = [n for n in subs if n.located]
    checks.append(
        _check(
            "substations_located",
            "Subestaciones con coordenadas",
            "ok" if len(located) / len(subs) > 0.9 else "warn",
            f"{len(located)}/{len(subs)}",
            "> 90 %",
            "Las no ubicadas están en el registro CEN pero no en IDE Energía ni en PyPSA-CL.",
            [n.name for n in subs if not n.located],
        )
    )
    lon0, lat0, lon1, lat1 = CHILE_BBOX
    outside = [n for n in located if not (lon0 <= n.lon <= lon1 and lat0 <= n.lat <= lat1)]
    checks.append(
        _check(
            "inside_chile",
            "Nodos dentro del territorio",
            "ok" if len(outside) <= 2 else "warn",
            len(outside),
            "≤ 2 (interconexión con Argentina)",
            "Puntos fuera del rectángulo de Chile continental.",
            [f"{n.name} ({n.lat:.2f}, {n.lon:.2f})" for n in outside],
        )
    )
    regions_with = {n.region_code for n in located if n.region_code}
    all_regions = {c.region_code for c in s.comunas} or regions_with
    missing = sorted(all_regions - regions_with)
    checks.append(
        _check(
            "regions_covered",
            "Regiones con subestaciones",
            "ok" if not missing else "fail",
            f"{len(all_regions) - len(missing)}/{len(all_regions)}",
            "16/16",
            "",
            missing,
        )
    )
    lats = [n.lat for n in sen_subs if n.located]
    if lats:
        checks.append(
            _check(
                "latitude_span",
                "Extensión norte-sur del SEN",
                "ok" if max(lats) > -19 and min(lats) < -42 else "warn",
                f"{max(lats):.2f}° a {min(lats):.2f}°",
                "de Arica (-18,5°) a Chiloé (-43°)",
            )
        )

    # comuna declared by IDE vs census polygon containing the point
    shapes = [(cut, _bbox(g), g) for cut, g in s.comuna_geometry.items() if g]
    if shapes:
        agree = total = 0
        bad = []
        for n in located:
            if not n.comuna_code:
                continue
            total += 1
            found = comuna_of_point(n.lon, n.lat, shapes)
            if found == str(int(n.comuna_code)):
                agree += 1
            else:
                bad.append(f"{n.name}: IDE {n.comuna_code} / polígono INE {found}")
        rate = agree / total if total else 0
        checks.append(
            _check(
                "comuna_consistency",
                "Comuna declarada (IDE) vs polígono comunal (INE)",
                "ok" if rate > 0.9 else "warn",
                f"{rate:.1%} ({agree}/{total})",
                "> 90 %",
                "Diferencias típicas: subestaciones sobre el límite comunal o geometría simplificada.",
                bad,
            )
        )

    # ---------- connectivity ----------
    g = nx.MultiGraph()
    g.add_nodes_from(nodes)
    for e in s.edges:
        g.add_edge(e.source_node, e.target_node, key=e.id, km=e.length_km or 0.0)
    main = max(nx.connected_components(g), key=len)
    big = [n for n in sen_subs if (n.kv or 0) >= 220]
    in_main = [n for n in big if n.id in main]
    checks.append(
        _check(
            "hv_in_main",
            "S/E SEN de 220 kV o más en la red principal",
            "ok" if len(in_main) / max(1, len(big)) > 0.9 else "warn",
            f"{len(in_main)}/{len(big)}",
            "> 90 %",
            "Las que quedan fuera no tienen líneas en las fuentes públicas.",
            [n.name for n in big if n.id not in main],
        )
    )
    main_lats = [nodes[i].lat for i in main if nodes[i].located]
    if main_lats:
        north = max((nodes[i] for i in main if nodes[i].located), key=lambda n: n.lat)
        south = min(
            (nodes[i] for i in main if nodes[i].located and (nodes[i].system or "SEN") == "SEN"),
            key=lambda n: n.lat,
        )
        try:
            km = nx.shortest_path_length(nx.Graph(g), north.id, south.id, weight="km")
            checks.append(
                _check(
                    "north_south_path",
                    "Camino eléctrico de extremo a extremo",
                    "ok",
                    f"{north.name} → {south.name}: {km:,.0f} km",
                    "existe un camino continuo",
                )
            )
        except nx.NetworkXNoPath:
            checks.append(
                _check(
                    "north_south_path",
                    "Camino eléctrico de extremo a extremo",
                    "fail",
                    "sin camino",
                    "existe",
                )
            )
    op_mw = [p for p in s.plants if p.operating and p.system == "SEN"]
    mw_main = sum(p.mw for p in op_mw if p.node in main)
    mw_all = sum(p.mw for p in op_mw) or 1
    checks.append(
        _check(
            "generation_connected",
            "Potencia SEN conectada a la red principal",
            "ok" if mw_main / mw_all > 0.95 else "warn",
            f"{mw_main / mw_all:.1%} ({mw_main:,.0f} de {mw_all:,.0f} MW)",
            "> 95 %",
        )
    )
    pop_main = sum(n.served_population for n in s.nodes if n.id in main)
    pop_all = sum(n.served_population for n in s.nodes) or 1
    checks.append(
        _check(
            "population_connected",
            "Población abastecida desde la red principal",
            "ok" if pop_main / pop_all > 0.95 else "warn",
            f"{pop_main / pop_all:.1%}",
            "> 95 % (Aysén y Magallanes son sistemas aparte)",
        )
    )
    sub_index = defaultdict(list)
    for n in subs:
        sub_index[" ".join(n.name.upper().replace("S/E ", "").split())].append(n.id)
    g500 = nx.Graph()
    site_of = {n.id: n.site for n in s.nodes}
    for e in lines:
        if (e.kv or 0) >= 500:
            g500.add_edge(site_of[e.source_node], site_of[e.target_node])
    missing_corr = []
    for a, b in BACKBONE_500:
        sa = {
            site_of[i]
            for k, ids in sub_index.items()
            if k == a or k.startswith(a + " (") or k == "SECCIONADORA " + a
            for i in ids
        }
        sb = {
            site_of[i]
            for k, ids in sub_index.items()
            if k == b or k.startswith(b + " (") or k == "SECCIONADORA " + b
            for i in ids
        }
        ok = any(x in g500 and y in g500 and nx.has_path(g500, x, y) for x in sa for y in sb)
        if not ok:
            missing_corr.append(f"{a} – {b}")
    checks.append(
        _check(
            "backbone_500",
            "Corredores troncales de 500 kV",
            "ok" if not missing_corr else "warn",
            f"{len(BACKBONE_500) - len(missing_corr)}/{len(BACKBONE_500)}",
            "todos conectados a 500 kV",
            "",
            missing_corr,
        )
    )

    # ---------- cross-source agreement ----------
    named = [
        e
        for e in lines
        if e.topology_source.startswith("inferida")
        and not any("tap" in (p.method or "") for p in e.provenance if p.field == "extremos")
    ]
    agree = 0
    for e in named:
        a, b = nodes[e.source_node], nodes[e.target_node]
        if a.kind == NodeKind.SUBSTATION and b.kind == NodeKind.SUBSTATION:
            toks = line_ends(e.name)
            agree += name_score(a.name, toks) >= 0.82 and name_score(b.name, toks) >= 0.82
    both = sum(
        1
        for e in named
        if nodes[e.source_node].kind == NodeKind.SUBSTATION
        and nodes[e.target_node].kind == NodeKind.SUBSTATION
    )
    checks.append(
        _check(
            "line_name_vs_ends",
            "Nombre de la línea coincide con sus extremos inferidos",
            "ok" if agree / max(1, both) > 0.85 else "warn",
            f"{agree / max(1, both):.1%} ({agree}/{both})",
            "> 85 %",
            "Excluye tramos cortados por derivaciones; las diferencias restantes suelen ser S/E con nombre comercial distinto.",
        )
    )
    cs = s.stats.get("cen_sections", {})
    confirmed = cs.get("confirmed_direct", 0) + cs.get("confirmed_via_taps", 0)
    resolved = cs.get("sections", 0) - cs.get("unresolved_end", 0) - cs.get("self_loop", 0)
    checks.append(
        _check(
            "cen_sections_confirmed",
            "Tramos oficiales CEN confirmados por el trazado IDE",
            "ok" if confirmed / max(1, resolved) > 0.6 else "warn",
            f"{confirmed}/{resolved}",
            "> 60 %",
            f"{cs.get('added_from_cen', 0)} tramos se agregaron como rectas esquemáticas; "
            f"{cs.get('unresolved_end', 0)} tienen un extremo no identificable.",
        )
    )
    ratio_bad = []
    for e in lines:
        if e.geometry_source == "IDE Energía" and e.coords and e.length_km and e.length_km > 2:
            geo = sum(haversine_km(*e.coords[i], *e.coords[i + 1]) for i in range(len(e.coords) - 1))
            if geo > 0 and not 0.6 <= e.length_km / geo <= 1.6:
                ratio_bad.append(f"{e.name}: declarada {e.length_km:.1f} km, trazado {geo:.1f} km")
    checks.append(
        _check(
            "length_vs_geometry",
            "Longitud declarada vs trazado",
            "ok" if len(ratio_bad) < 0.05 * len(lines) else "warn",
            f"{len(ratio_bad)} fuera de rango",
            "< 5 % de las líneas",
            "Rango aceptado 0,6 a 1,6.",
            ratio_bad,
        )
    )
    mb = s.stats.get("model_buses", 0)
    checks.append(
        _check(
            "model_buses_matched",
            "Barras PyPSA-CL asociadas a una subestación",
            "ok" if s.stats.get("model_buses_matched", 0) / max(1, mb) > 0.9 else "warn",
            f"{s.stats.get('model_buses_matched', 0)}/{mb}",
            "> 90 %",
            "",
            [b.name for b in s.model_buses if not b.node],
        )
    )

    # ---------- physical plausibility ----------
    x_bad = []
    with_x = 0
    for e in lines:
        el = e.electrical
        if not el or not el.x_ohm or not e.length_km or e.length_km < 5:
            continue
        cls = min(X_PER_KM, key=lambda k: abs(k - (e.kv or 0)))
        lo, hi = X_PER_KM[cls]
        with_x += 1
        n_par = (
            max(1, len(next(b for b in s.model_branches if b.name == el.branch).edges)) if el.branch else 1
        )
        x_km = el.x_ohm * n_par / e.length_km
        if not lo / 3 <= x_km <= hi * 3:
            x_bad.append(f"{e.name}: {x_km:.2f} Ω/km por circuito")
    checks.append(
        _check(
            "reactance_per_km",
            "Reactancia por km dentro del rango típico",
            "ok" if len(x_bad) < 0.2 * max(1, with_x) else "warn",
            f"{with_x - len(x_bad)}/{with_x}",
            "< 20 % fuera de rango",
            "Rango típico por tensión con tolerancia x3; diferencias grandes indican que el corredor del modelo no coincide con el tramo físico.",
            x_bad,
        )
    )
    pop_census = sum(c.population for c in s.comunas)
    checks.append(
        _check(
            "census_total",
            "Población censal cargada vs total oficial",
            "ok" if abs(pop_census - OFFICIAL_POPULATION_2024) < 1000 else "warn",
            f"{pop_census:,}",
            f"{OFFICIAL_POPULATION_2024:,} (INE)",
        )
    )
    pop_assigned = sum(n.served_population for n in s.nodes)
    checks.append(
        _check(
            "population_assigned",
            "Población asignada a subestaciones",
            "ok" if abs(pop_assigned - pop_census) / max(1, pop_census) < 0.001 else "warn",
            f"{pop_assigned:,.0f}",
            f"{pop_census:,} (toda la población censal)",
        )
    )
    mw_sen = sum(p.mw for p in op_mw)
    checks.append(
        _check(
            "installed_capacity",
            "Potencia instalada SEN en operación",
            "ok" if 30_000 < mw_sen < 45_000 else "warn",
            f"{mw_sen:,.0f} MW",
            "30 a 45 GW (orden de magnitud CEN 2026)",
        )
    )
    status = Counter(c["status"] for c in checks)
    return {"summary": dict(status), "checks": checks}
