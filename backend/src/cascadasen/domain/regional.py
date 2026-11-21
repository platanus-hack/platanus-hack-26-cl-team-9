"""Regional grids (context layer, docs/regional.md): one common schema for other countries.

Pure functions and data, no I/O. Source adapters deliver a `RegionalBundle` in the raw units of
their source; `normalise` filters, deduplicates and simplifies it, and `feature_collections`
turns it into the GeoJSON the map reads. Nothing here feeds the physics: the other countries are
drawn, never simulated.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cascadasen.domain.geo import douglas_peucker, polyline_km

TECHS = ("solar", "eolica", "hidro", "termica", "bioenergia", "geotermica", "nuclear")
MIN_PLANT_MW = 0.1  # smaller units are noise at country zoom
MIN_KV = 66.0  # lower voltages are distribution and would drown the map
LINE_TOLERANCE_M = 150.0
EARTH_R = 6371008.8

_FUEL_WORDS = (
    ("nuclear", "nuclear"),
    ("geoterm", "geotermica"),
    ("solar", "solar"),
    ("fotovolt", "solar"),
    ("photovolt", "solar"),
    ("eolic", "eolica"),
    ("wind", "eolica"),
    ("viento", "eolica"),
    ("hidr", "hidro"),
    ("hydro", "hidro"),
    ("water", "hidro"),
    ("biomas", "bioenergia"),
    ("biogas", "bioenergia"),
    ("biofuel", "bioenergia"),
    ("bagaz", "bioenergia"),
    ("waste", "bioenergia"),
    ("termic", "termica"),
    ("termo", "termica"),
    ("thermal", "termica"),
    ("diesel", "termica"),
    ("gas", "termica"),
    ("coal", "termica"),
    ("carb", "termica"),
    ("oil", "termica"),
    ("fuel", "termica"),
    ("petrol", "termica"),
    ("vapor", "termica"),
    ("ciclo", "termica"),
    ("turbina", "termica"),
    ("motor", "termica"),
)


@dataclass(frozen=True)
class RegionalSource:
    id: str
    name: str
    publisher: str
    url: str
    license: str
    attribution: str
    provides: tuple[str, ...]
    fetched_at: str | None = None


@dataclass
class RegionalLine:
    record: str
    name: str
    kv: float | None
    coords: list[tuple[float, float]]
    source: str
    kv_levels: list[float] = field(default_factory=list)
    circuits: int | None = None
    length_km: float | None = None
    status: str | None = None


@dataclass
class RegionalSubstation:
    record: str
    name: str
    kv: float | None
    lon: float
    lat: float
    source: str
    kv_levels: list[float] = field(default_factory=list)


@dataclass
class RegionalPlant:
    record: str
    name: str
    tech: str | None
    mw: float | None
    lon: float
    lat: float
    source: str
    status: str | None = None
    fuel: str | None = None
    operating: bool = True


@dataclass
class RegionalBundle:
    country: str  # ISO 3166-1 alpha-3
    country_name: str
    sources: list[RegionalSource] = field(default_factory=list)
    lines: list[RegionalLine] = field(default_factory=list)
    substations: list[RegionalSubstation] = field(default_factory=list)
    plants: list[RegionalPlant] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_kv_levels(raw: Any) -> list[float]:
    """Voltages in kV, highest first. Accepts 220, "220", "220,5", "220 kV", OSM "500000;220000"."""
    if raw is None:
        return []
    if isinstance(raw, int | float):
        parts: Iterable[str] = [str(raw)]
    else:
        parts = re.split(r"[;/|]", str(raw))
    levels: list[float] = []
    for part in parts:
        m = re.search(r"\d+(?:[.,]\d+)?", part)
        if not m:
            continue
        value = float(m.group().replace(",", "."))
        if value >= 1000 and "kv" not in part.lower():  # OSM stores volts
            value /= 1000
        if 0 < value <= 1500:
            levels.append(round(value, 3))
    return sorted(set(levels), reverse=True)


def tech_from_text(text: str | None) -> str | None:
    """Map a free-text fuel or technology label to the map vocabulary (`TECHS`)."""
    if not text:
        return None
    low = text.lower()
    for word, tech in _FUEL_WORDS:
        if word in low:
            return tech
    return None


def _project(coords: Sequence[tuple[float, float]]) -> np.ndarray:
    ll = np.asarray(coords, dtype=float)
    lon0 = float(ll[:, 0].mean())
    lat_r = np.radians(ll[:, 1])
    return np.c_[EARTH_R * np.radians(ll[:, 0] - lon0) * np.cos(lat_r), EARTH_R * lat_r]


def simplify_line(
    coords: Sequence[tuple[float, float]], tol_m: float = LINE_TOLERANCE_M
) -> list[tuple[float, float]]:
    """Douglas-Peucker with a projection centred on the line itself (the Chile one distorts Brazil)."""
    if len(coords) <= 2:
        return [(round(lon, 5), round(lat, 5)) for lon, lat in coords]
    keep = douglas_peucker(_project(coords), tol_m)
    return [(round(coords[k][0], 5), round(coords[k][1], 5)) for k in keep]


def _in_range(lon: float, lat: float) -> bool:
    return -120.0 <= lon <= -30.0 and -60.0 <= lat <= 35.0


def normalise(bundle: RegionalBundle, min_kv: float = MIN_KV) -> RegionalBundle:
    """Filter to the transmission network, drop duplicates, simplify and fill missing lengths."""
    out = RegionalBundle(
        bundle.country, bundle.country_name, list(bundle.sources), warnings=list(bundle.warnings)
    )

    no_kv = low_kv = bad = 0
    for line in bundle.lines:
        if len(line.coords) < 2 or not all(_in_range(*c) for c in line.coords):
            bad += 1
            continue
        if line.kv is None:
            no_kv += 1
            continue
        if line.kv < min_kv:
            low_kv += 1
            continue
        length = line.length_km if line.length_km else polyline_km(line.coords)
        out.lines.append(
            RegionalLine(
                record=line.record,
                name=line.name,
                kv=line.kv,
                coords=simplify_line(line.coords),
                source=line.source,
                kv_levels=line.kv_levels or [line.kv],
                circuits=line.circuits,
                length_km=round(length, 2),
                status=line.status,
            )
        )
    if no_kv:
        out.warnings.append(f"{no_kv} líneas sin tensión descartadas")
    if low_kv:
        out.warnings.append(f"{low_kv} líneas de menos de {min_kv:g} kV descartadas")
    if bad:
        out.warnings.append(f"{bad} líneas con geometría inválida descartadas")

    seen: set[tuple[str, float, float]] = set()
    dropped = 0
    for s in bundle.substations:
        if not _in_range(s.lon, s.lat) or s.kv is None or s.kv < min_kv:
            dropped += 1
            continue
        key = (s.name.strip().lower(), round(s.lon, 3), round(s.lat, 3))
        if key in seen:
            continue
        seen.add(key)
        out.substations.append(s)
    if dropped:
        out.warnings.append(f"{dropped} subestaciones sin tensión o bajo {min_kv:g} kV descartadas")

    seen_plants: set[tuple[str, float, float]] = set()
    for p in bundle.plants:
        if not p.operating or not p.mw or p.mw < MIN_PLANT_MW or not _in_range(p.lon, p.lat):
            continue
        key = (p.name.strip().lower(), round(p.lon, 3), round(p.lat, 3))
        if key in seen_plants:
            continue
        seen_plants.add(key)
        out.plants.append(p)
    return out


def _props(country: str, kind: str, n: int, source: str, record: str, name: str) -> dict[str, Any]:
    return {
        "id": f"{country}-{kind}{n}",
        "country": country,
        "name": name,
        "source": source,
        "source_record": record,
        "is_assumption": False,
    }


def feature_collections(bundle: RegionalBundle) -> dict[str, dict[str, Any]]:
    """GeoJSON per layer (`lines`, `substations`, `plants`) with the common property names."""
    c = bundle.country
    lines = []
    for i, ln in enumerate(sorted(bundle.lines, key=lambda x: (-(x.kv or 0), x.name, x.record)), 1):
        props = _props(c, "L", i, ln.source, ln.record, ln.name) | {
            "kv": ln.kv,
            "kv_levels": ln.kv_levels,
            "circuits": ln.circuits,
            "length_km": ln.length_km,
            "status": ln.status,
        }
        lines.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": ln.coords},
                "properties": props,
            }
        )
    subs = []
    for i, s in enumerate(sorted(bundle.substations, key=lambda x: (-(x.kv or 0), x.name, x.record)), 1):
        props = _props(c, "S", i, s.source, s.record, s.name) | {
            "kv": s.kv,
            "kv_levels": s.kv_levels or [s.kv],
        }
        subs.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(s.lon, 5), round(s.lat, 5)]},
                "properties": props,
            }
        )
    plants = []
    for i, p in enumerate(sorted(bundle.plants, key=lambda x: (-(x.mw or 0), x.name, x.record)), 1):
        props = _props(c, "P", i, p.source, p.record, p.name) | {
            "tech": p.tech,
            "mw": round(p.mw or 0, 2),
            "status": p.status,
            "fuel": p.fuel,
        }
        plants.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(p.lon, 5), round(p.lat, 5)]},
                "properties": props,
            }
        )
    wrap = lambda feats: {"type": "FeatureCollection", "features": feats}  # noqa: E731
    return {"lines": wrap(lines), "substations": wrap(subs), "plants": wrap(plants)}


def manifest_entry(bundle: RegionalBundle) -> dict[str, Any]:
    """Counts, km per voltage and sources of one country, for `manifest.json` and the UI legend."""
    km_by_kv: dict[str, float] = {}
    for ln in bundle.lines:
        key = f"{ln.kv:g}"
        km_by_kv[key] = round(km_by_kv.get(key, 0.0) + (ln.length_km or 0.0), 1)
    mw_by_tech: dict[str, float] = {}
    for p in bundle.plants:
        key = p.tech or "otra"
        mw_by_tech[key] = round(mw_by_tech.get(key, 0.0) + (p.mw or 0.0), 1)
    lons = [c[0] for ln in bundle.lines for c in ln.coords] + [s.lon for s in bundle.substations]
    lats = [c[1] for ln in bundle.lines for c in ln.coords] + [s.lat for s in bundle.substations]
    return {
        "country": bundle.country,
        "name": bundle.country_name,
        "counts": {
            "lines": len(bundle.lines),
            "substations": len(bundle.substations),
            "plants": len(bundle.plants),
        },
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
            for s in bundle.sources
        ],
        "warnings": bundle.warnings,
    }


__all__ = [
    "MIN_KV",
    "TECHS",
    "RegionalBundle",
    "RegionalLine",
    "RegionalPlant",
    "RegionalSource",
    "RegionalSubstation",
    "feature_collections",
    "manifest_entry",
    "normalise",
    "parse_kv_levels",
    "simplify_line",
    "tech_from_text",
]
