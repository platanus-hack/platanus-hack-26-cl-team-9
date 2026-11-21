"""Adapter: INE Censo 2024 (ArcGIS FeatureServer behind visualizador.ine.gob.cl). Population."""

from __future__ import annotations

import numpy as np

from cascadasen.domain.geo import douglas_peucker, project
from cascadasen.domain.model import RawCensusZone, RawComuna, SourceBundle, SourceInfo
from cascadasen.infrastructure.arcgis import query_layer
from cascadasen.infrastructure.http import CachedHttp
from cascadasen.infrastructure.sources.ide_energia import _mtime

COMUNAS_LAYER = 11
ZONES_LAYER = 2
DISPLAY_TOL_M = 250.0  # national-scale display geometry
MIN_ISLAND_KM2 = 1.0


def display_geometry(geom: dict | None, tol_m: float = DISPLAY_TOL_M) -> dict | None:
    """Simplify a comuna polygon for a national map: Douglas-Peucker on the outer rings, holes
    dropped, islets under MIN_ISLAND_KM2 dropped (the largest polygon is always kept)."""
    if not geom:
        return None
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    kept: list[tuple[float, list]] = []
    for poly in polys:
        ring = np.asarray(poly[0], dtype=float)[:, :2]
        if len(ring) < 4:
            continue
        xy = project(ring[:, 0], ring[:, 1])
        area_km2 = abs(np.dot(xy[:-1, 0], xy[1:, 1]) - np.dot(xy[1:, 0], xy[:-1, 1])) / 2e6
        keep = douglas_peucker(xy, tol_m)
        if len(keep) < 4:
            keep = [*list(range(0, len(ring), max(1, len(ring) // 4))), len(ring) - 1]
        coords = [[round(float(ring[k, 0]), 4), round(float(ring[k, 1]), 4)] for k in keep]
        kept.append((area_km2, coords))
    if not kept:
        return None
    kept.sort(key=lambda t: -t[0])
    out = [[c] for i, (a, c) in enumerate(kept) if i == 0 or a >= MIN_ISLAND_KM2]
    return (
        {"type": "Polygon", "coordinates": out[0]}
        if len(out) == 1
        else {"type": "MultiPolygon", "coordinates": out}
    )


class IneCensoSource:
    source_id = "ine_censo2024"

    def __init__(self, http: CachedHttp, base_url: str, simplify_deg: float = 0.002) -> None:
        self.http = http
        self.base = base_url.rstrip("/")
        self.simplify_deg = simplify_deg

    def contribute(self, bundle: SourceBundle, refresh: bool = False) -> SourceInfo:
        fields = "CUT,COMUNA,COD_REGION,REGION,PROVINCIA,n_per,n_hog,n_vp"
        shapes = query_layer(
            self.http,
            f"{self.base}/{COMUNAS_LAYER}",
            f"{self.source_id}/comunas.geojson",
            refresh,
            page_size=400,
            outFields=fields,
            maxAllowableOffset=self.simplify_deg,
            geometryPrecision=5,
        )
        centroids = query_layer(
            self.http,
            f"{self.base}/{COMUNAS_LAYER}",
            f"{self.source_id}/comunas_centroides.json",
            refresh,
            page_size=2000,
            fmt="json",
            outFields="CUT",
            returnGeometry="false",
            returnCentroid="true",
        )
        cent = {
            str(c["attributes"]["CUT"]): (c["centroid"]["x"], c["centroid"]["y"])
            for c in centroids
            if c.get("centroid")
        }
        for f in shapes:
            p = f["properties"]
            cut = str(int(p["CUT"]))
            bundle.comunas.append(
                RawComuna(
                    source=self.source_id,
                    cut=cut,
                    name=(p.get("COMUNA") or "").title(),
                    region_code=f"{int(p['COD_REGION']):02d}",
                    region_name=(p.get("REGION") or "").title(),
                    province_name=(p.get("PROVINCIA") or "").title() or None,
                    population=int(p.get("n_per") or 0),
                    households=p.get("n_hog"),
                    dwellings=p.get("n_vp"),
                    centroid=cent.get(cut),
                    geometry=display_geometry(f.get("geometry")),
                )
            )
        zones = query_layer(
            self.http,
            f"{self.base}/{ZONES_LAYER}",
            f"{self.source_id}/zonas_censales.json",
            refresh,
            page_size=2000,
            fmt="json",
            outFields="OBJECTID,CUT,AREA_C,n_per",
            returnGeometry="false",
            returnCentroid="true",
        )
        for z in zones:
            a, c = z["attributes"], z.get("centroid")
            if not c or not a.get("n_per"):
                continue
            bundle.census_zones.append(
                RawCensusZone(
                    self.source_id,
                    str(a["OBJECTID"]),
                    str(int(a["CUT"])),
                    int(a["n_per"]),
                    c["x"],
                    c["y"],
                    a.get("AREA_C") == "URBANO",
                )
            )
        return SourceInfo(
            id=self.source_id,
            name="Censo de Población y Vivienda 2024: comunas y zonas censales",
            publisher="Instituto Nacional de Estadísticas (INE)",
            url=self.base,
            provides=(
                "límites comunales",
                "población, hogares y viviendas por comuna",
                "población por zona censal urbana",
            ),
            records=len(shapes) + len(zones),
            fetched_at=_mtime(self.http.cached(f"{self.source_id}/comunas.geojson")),
            notes=f"Geometría comunal simplificada para escala nacional ({DISPLAY_TOL_M:.0f} m, sin islotes < {MIN_ISLAND_KM2:g} km²).",
        )
