"""Adapter: Ministerio de Energía, IDE Energía (ArcGIS MapServer). Locations and line geometry."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from cascadasen.domain.geo import utm_to_lonlat
from cascadasen.domain.model import RawLine, RawPlant, RawStorage, RawSubstation, SourceBundle, SourceInfo
from cascadasen.infrastructure.arcgis import query_layer
from cascadasen.infrastructure.http import CachedHttp

PLANT_LAYERS = {
    1: ("bioenergia", "bioenergia", "BIO"),
    2: ("geotermicas", "geotermica", "GEO"),
    3: ("eolicas", "eolica", "EOL"),
    4: ("solares", "solar", "SOL"),
    5: ("termoelectricas", "termica", "TER"),
    6: ("hidroelectricas", "hidro", "HID"),
}
OPERATING = {"OPERATIVA", "EN OPERACION"}  # the layers use both labels for the same state


def _kv(raw) -> float | None:
    try:
        return float(str(raw).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _str(v) -> str | None:
    return str(v).strip() if v not in (None, "") else None


class IdeEnergiaSource:
    source_id = "ide_energia"

    def __init__(self, http: CachedHttp, base_url: str) -> None:
        self.http = http
        self.base = base_url

    def _layer(self, layer: int, name: str, refresh: bool) -> list[dict]:
        return query_layer(self.http, f"{self.base}/{layer}", f"{self.source_id}/{name}.geojson", refresh)

    def contribute(self, bundle: SourceBundle, refresh: bool = False) -> SourceInfo:
        """Read the IDE layers (from the HTTP cache unless `refresh`) and append them to the bundle.

        Layers: 8 substations, 10 transmission lines, 1 to 6 plants (one per technology) and 9 storage. The
        lines have no end nodes, so the topology is inferred later. A multi-part line keeps its first part in
        `coords` and all parts in `extra["parts"]`. `operating` is true for both labels the plant layers use for
        that state. The storage layer ships without geometry, so its position comes from the UTM attributes (zone
        from `HUSO`, 19 by default). `records` in the returned `SourceInfo` counts everything appended."""
        n = 0
        for f in self._layer(8, "subestaciones", refresh):
            p, g = f["properties"], f.get("geometry")
            lon, lat = g["coordinates"][:2] if g else (None, None)
            bundle.substations.append(
                RawSubstation(
                    source=self.source_id,
                    record_id=str(p["OBJECTID"]),
                    name=(p.get("NOMBRE") or "").strip(),
                    lon=lon,
                    lat=lat,
                    kv=_kv(p.get("TENSION_KV")),
                    segment=_str(p.get("TIPO")),
                    system=_str(p.get("SIST_ELECT")),
                    owner=_str(p.get("PROPIEDAD")),
                    region_code=_str(p.get("REGION")),
                    comuna_code=_str(p.get("COMUNA")),
                    cen_id=int(p["ID_SUBEST"]) if p.get("ID_SUBEST") is not None else None,
                    extra={"kv_raw": p.get("TENSION_KV"), "fuente_base": p.get("FUENTE_BAS")},
                )
            )
            n += 1
        for f in self._layer(10, "lineas_transmision", refresh):
            p, g = f["properties"], f.get("geometry")
            if not g or not g.get("coordinates"):
                continue
            parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
            parts = [[(float(c[0]), float(c[1])) for c in part] for part in parts if len(part) >= 2]
            if not parts:
                continue
            bundle.geo_lines.append(
                RawLine(
                    source=self.source_id,
                    record_id=str(p["OBJECTID"]),
                    name=(p.get("NOMBRE") or "").strip(),
                    kv=_kv(p.get("TENSION_KV")),
                    circuit=_str(p.get("CIRCUITO")),
                    segment=_str(p.get("TIPO")),
                    system=_str(p.get("SIST_ELECT")),
                    owner=_str(p.get("PROPIEDAD")),
                    length_km=p.get("LONG_KM"),
                    coords=parts[0],
                    status=_str(p.get("ESTADO")),
                    extra={"tramo": _str(p.get("TRAMO")), "parts": parts if len(parts) > 1 else None},
                )
            )
            n += 1
        for layer, (name, tech, prefix) in PLANT_LAYERS.items():
            for f in self._layer(layer, f"centrales_{name}", refresh):
                p, g = f["properties"], f.get("geometry")
                if not g:
                    continue
                bundle.plants.append(
                    RawPlant(
                        source=self.source_id,
                        record_id=f"{prefix}{p['OBJECTID']}",
                        name=(p.get("NOMBRE") or "").strip(),
                        tech=tech,
                        mw=p.get("POTENCIAMW"),
                        lon=g["coordinates"][0],
                        lat=g["coordinates"][1],
                        status=_str(p.get("ESTADO")),
                        operating=p.get("ESTADO") in OPERATING,
                        system=_str(p.get("SIST_ELECT")),
                        owner=_str(p.get("PROPIEDAD")),
                        fuel=_str(p.get("COMBUSTIBL")),
                        region_code=_str(p.get("REGION")),
                        comuna_code=_str(p.get("COMUNA")),
                    )
                )
                n += 1
        for f in self._layer(9, "almacenamiento", refresh):
            p, g = f["properties"], f.get("geometry")
            if g:
                lon, lat = g["coordinates"][:2]
            else:  # the storage layer ships without geometry; rebuild it from the UTM attributes
                zone = int(re.sub(r"\D", "", p.get("HUSO") or "19"))
                lon, lat = utm_to_lonlat(float(p["COORD_ESTE"]), float(p["COORD_NORT"]), zone)
            bundle.storage.append(
                RawStorage(
                    source=self.source_id,
                    record_id=str(p["OBJECTID"]),
                    name=(p.get("NOMBRE") or "").strip(),
                    lon=round(lon, 6),
                    lat=round(lat, 6),
                    equipment=_str(p.get("TIPO_EQUIPO")),
                    owner=_str(p.get("PROPIEDAD")),
                    substation_name=_str(p.get("NOMBRE_SE")),
                )
            )
            n += 1
        cached = self.http.cached(f"{self.source_id}/subestaciones.geojson")
        return SourceInfo(
            id=self.source_id,
            name="IDE Energía: capas de generación, transmisión y almacenamiento",
            publisher="Ministerio de Energía (datos de origen CEN, SEC, CNE)",
            url=self.base,
            provides=(
                "ubicación de subestaciones",
                "trazado de líneas",
                "centrales (MW, tecnología)",
                "baterías",
            ),
            records=n,
            fetched_at=_mtime(cached),
            notes="Sin extremos de línea: la topología se infiere por geometría y nombre.",
        )


def _mtime(path) -> str | None:
    if not path:
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds")
