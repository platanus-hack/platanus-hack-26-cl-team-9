"""Adapter: OpenStreetMap power data through the Overpass API (used where there is no official GIS)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

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

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_UNITS = {"w": 1e-6, "kw": 1e-3, "mw": 1.0, "gw": 1e3}


def parse_mw(raw: str | None) -> float | None:
    """OSM `plant:output:electricity`: "120 MW", "1.5 GW", "500 kW", "30" (no unit means MW)."""
    if not raw:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*([a-zA-Z]*)", raw)
    if not m:
        return None
    unit = m.group(2).lower() or "mw"
    if unit not in _UNITS:
        return None
    return float(m.group(1).replace(",", ".")) * _UNITS[unit]


def _query(iso2: str, selector: str, out: str) -> str:
    return f'[out:json][timeout:240];area["ISO3166-1"="{iso2}"]->.a;({selector}(area.a););{out};'


class OsmOverpassSource:
    def __init__(
        self, http: CachedHttp, country: str, country_name: str, iso2: str, url: str = OVERPASS_URL
    ) -> None:
        self.http = http
        self.country = country
        self.country_name = country_name
        self.iso2 = iso2
        self.url = url

    def _elements(self, name: str, selector: str, out: str, refresh: bool) -> list[dict[str, Any]]:
        data = self.http.get_json(
            self.url,
            f"regional/{self.country.lower()}/osm_{name}.json",
            refresh=refresh,
            params={"data": _query(self.iso2, selector, out)},
        )
        return data.get("elements", [])

    def fetch(self, refresh: bool = False) -> RegionalBundle:
        src = "OpenStreetMap"
        bundle = RegionalBundle(self.country, self.country_name)
        bundle.sources.append(
            RegionalSource(
                id="osm_power",
                name="OpenStreetMap, etiquetas power=*",
                publisher="Colaboradores de OpenStreetMap",
                url="https://www.openstreetmap.org/",
                license="ODbL 1.0",
                attribution="© OpenStreetMap contributors",
                provides=("lines", "substations", "plants"),
                fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        )
        for el in self._elements(
            "lines", 'way["power"~"^(line|cable)$"]["voltage"]', "out geom tags", refresh
        ):
            geom = el.get("geometry") or []
            tags = el.get("tags", {})
            levels = parse_kv_levels(tags.get("voltage"))
            bundle.lines.append(
                RegionalLine(
                    record=f"way/{el['id']}",
                    name=(tags.get("name") or tags.get("ref") or "").strip(),
                    kv=levels[0] if levels else None,
                    kv_levels=levels,
                    coords=[(float(p["lon"]), float(p["lat"])) for p in geom],
                    source=src,
                    circuits=int(tags["circuits"]) if str(tags.get("circuits", "")).isdigit() else None,
                    status="operación" if tags.get("construction") is None else "construcción",
                )
            )
        for el in self._elements("substations", 'nwr["power"="substation"]', "out center tags", refresh):
            c = el.get("center") or el
            if "lon" not in c:
                continue
            tags = el.get("tags", {})
            levels = parse_kv_levels(tags.get("voltage"))
            bundle.substations.append(
                RegionalSubstation(
                    record=f"{el['type']}/{el['id']}",
                    name=(tags.get("name") or tags.get("ref") or "").strip(),
                    kv=levels[0] if levels else None,
                    kv_levels=levels,
                    lon=float(c["lon"]),
                    lat=float(c["lat"]),
                    source=src,
                )
            )
        for el in self._elements("plants", 'nwr["power"="plant"]', "out center tags", refresh):
            c = el.get("center") or el
            if "lon" not in c:
                continue
            tags = el.get("tags", {})
            fuel = tags.get("plant:source") or tags.get("generator:source") or ""
            bundle.plants.append(
                RegionalPlant(
                    record=f"{el['type']}/{el['id']}",
                    name=(tags.get("name") or "").strip(),
                    tech=tech_from_text(fuel) or tech_from_text(tags.get("plant:method")),
                    mw=parse_mw(tags.get("plant:output:electricity")),
                    lon=float(c["lon"]),
                    lat=float(c["lat"]),
                    source=src,
                    fuel=fuel or None,
                    operating=tags.get("construction") is None and "proposed" not in tags.get("power", ""),
                )
            )
        if not bundle.lines:
            bundle.warnings.append("OSM no devolvió líneas con tensión")
        return bundle
