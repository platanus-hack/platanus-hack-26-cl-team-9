"""Adapter: Secretaría de Energía de Argentina (datos.energia.gob.ar), CSV open datasets.

NOT VERIFIED AGAINST REAL FILES: the server was unreachable when this was written (2026-11-21), so
the column names are detected by candidate lists and the geometry is read from a GeoJSON or WKT
column, or from latitude and longitude columns. Run `cascadasen-regional --countries ARG` once the
server answers and fix the candidate lists to the real header (docs/regional.md).
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import UTC, datetime

from cascadasen.domain.regional import (
    RegionalBundle,
    RegionalLine,
    RegionalPlant,
    RegionalSource,
    RegionalSubstation,
    parse_kv_levels,
    tech_from_text,
)
from cascadasen.infrastructure.http import CachedHttp

DATASETS = {
    "lines": "53014951-6ee1-4e99-a830-c4d0eb373496/resource/32c751ba-d887-4b6b-91bb-14e3f2639b51/download/transporte-elctrico-at-lneas.csv",
    "substations": "5ae5fbf9-5ab3-407b-a047-625bf27835aa/resource/cedb62c4-4a4c-4124-bdc9-48f611a59862/download/transporte-elctrico-at-estaciones-transformadoras.csv",
    "plants": "c62df6c6-73af-4039-b956-db081ff6eebe/resource/230fdf38-8f12-4017-a1e8-d7a1bc4a1c1c/download/generacin-elctrica-centrales-de-generacin.csv",
}
BASE_URL = "http://datos.energia.gob.ar/dataset"  # https refuses the connection

NAME = ("nombre", "name", "denominacion", "denominacion_estacion", "nombre_linea")
KV = ("tension", "tension_kv", "kv", "nivel_tension", "tension_nominal", "tension_nom")
MW = ("potencia_instalada", "potencia_mw", "potencia", "pot_inst", "potencia_instalada_mw", "mw")
TECH = ("tecnologia", "tipo_maquina", "fuente", "tipo", "tipo_generacion", "tipo_central")
STATUS = ("estado", "situacion")
GEOM = ("geojson", "geom", "the_geom", "wkt", "geometry", "geometria")
LON = ("longitud", "lon", "long", "x", "coordx")
LAT = ("latitud", "lat", "y", "coordy")


def _col(row: dict[str, str], names: tuple[str, ...]) -> str | None:
    lower = {k.strip().lower(): v for k, v in row.items() if k}
    for n in names:
        v = lower.get(n)
        if v not in (None, ""):
            return v.strip()
    return None


def _float(raw: str | None) -> float | None:
    try:
        return float(raw.replace(",", ".")) if raw else None
    except ValueError:
        return None


def _pairs(text: str) -> list[tuple[float, float]]:
    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    return [(float(nums[i]), float(nums[i + 1])) for i in range(0, len(nums) - 1, 2)]


def parse_geometry(raw: str | None) -> list[list[tuple[float, float]]]:
    """GeoJSON geometry text or WKT (LINESTRING, MULTILINESTRING, POINT) to a list of coordinate lists."""
    if not raw:
        return []
    raw = raw.strip()
    if raw.startswith("{"):
        g = json.loads(raw)
        kind, c = g.get("type"), g.get("coordinates")
        if kind == "LineString":
            return [[(float(x), float(y)) for x, y, *_ in c]]
        if kind == "MultiLineString":
            return [[(float(x), float(y)) for x, y, *_ in part] for part in c]
        if kind == "Point":
            return [[(float(c[0]), float(c[1]))]]
        return []
    upper = raw.upper()
    body = raw[raw.index("(") :] if "(" in raw else ""
    if upper.startswith("MULTILINESTRING"):
        return [_pairs(part) for part in re.findall(r"\(([^()]+)\)", body)]
    if upper.startswith("LINESTRING"):
        return [_pairs(body)]
    if upper.startswith("POINT"):
        return [_pairs(body)[:1]]
    return []


def _point(row: dict[str, str]) -> tuple[float, float] | None:
    parts = parse_geometry(_col(row, GEOM))
    if parts and parts[0]:
        return parts[0][0]
    lon, lat = _float(_col(row, LON)), _float(_col(row, LAT))
    return (lon, lat) if lon is not None and lat is not None else None


class EnergiaArgentinaSource:
    country = "ARG"

    def __init__(self, http: CachedHttp, base_url: str = BASE_URL) -> None:
        self.http = http
        self.base = base_url

    def _rows(self, layer: str, refresh: bool) -> list[dict[str, str]]:
        raw = self.http.get_bytes(f"{self.base}/{DATASETS[layer]}", f"regional/arg/{layer}.csv", refresh)
        text = raw.decode("utf-8-sig", errors="replace")
        return list(csv.DictReader(io.StringIO(text)))

    def fetch(self, refresh: bool = False) -> RegionalBundle:
        bundle = RegionalBundle(self.country, "Argentina")
        bundle.sources.append(
            RegionalSource(
                id="energia_ar",
                name="Secretaría de Energía, transporte eléctrico AT y centrales de generación",
                publisher="Secretaría de Energía, Argentina",
                url="https://datos.gob.ar/dataset/energia-transporte-electrico-at-lineas",
                license="No especificada en datos.gob.ar",
                attribution="Secretaría de Energía de la Nación (datos.energia.gob.ar)",
                provides=("lines", "substations", "plants"),
                fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        )
        src = "Secretaría de Energía"
        for i, row in enumerate(self._rows("lines", refresh)):
            levels = parse_kv_levels(_col(row, KV))
            for part in parse_geometry(_col(row, GEOM)):
                if len(part) >= 2:
                    bundle.lines.append(
                        RegionalLine(
                            record=str(_col(row, ("gid", "id", "objectid", "fid")) or i),
                            name=_col(row, NAME) or "",
                            kv=levels[0] if levels else None,
                            kv_levels=levels,
                            coords=part,
                            source=f"{src}, líneas AT",
                            status=_col(row, STATUS),
                        )
                    )
        for i, row in enumerate(self._rows("substations", refresh)):
            pt = _point(row)
            levels = parse_kv_levels(_col(row, KV))
            if pt:
                bundle.substations.append(
                    RegionalSubstation(
                        record=str(_col(row, ("gid", "id", "objectid", "fid")) or i),
                        name=_col(row, NAME) or "",
                        kv=levels[0] if levels else None,
                        kv_levels=levels,
                        lon=pt[0],
                        lat=pt[1],
                        source=f"{src}, estaciones transformadoras",
                    )
                )
        for i, row in enumerate(self._rows("plants", refresh)):
            pt = _point(row)
            tech_text = _col(row, TECH)
            if pt:
                bundle.plants.append(
                    RegionalPlant(
                        record=str(_col(row, ("gid", "id", "objectid", "fid")) or i),
                        name=_col(row, NAME) or "",
                        tech=tech_from_text(tech_text)
                        or tech_from_text(_col(row, ("combustible", "fuente"))),
                        mw=_float(_col(row, MW)),
                        lon=pt[0],
                        lat=pt[1],
                        source=f"{src}, centrales de generación",
                        status=_col(row, STATUS),
                        fuel=tech_text,
                    )
                )
        if not bundle.lines:
            bundle.warnings.append("No se pudo leer ninguna línea: revisar las columnas del CSV")
        return bundle
