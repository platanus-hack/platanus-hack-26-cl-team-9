"""Adapter: Osinergmin GISEM (Peru), ArcGIS MapServer of the SEIN in operation."""

from __future__ import annotations

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
from cascadasen.infrastructure.arcgis import query_layer
from cascadasen.infrastructure.http import CachedHttp

LINE_LAYERS = {28: 33, 29: 60, 30: 138, 31: 220, 32: 500}
SUBSTATION_LAYERS = {22: 33, 23: 60, 24: 138, 25: 220, 26: 500}
# layer -> (tech or None to read it from FUENTE_ENER, label)
PLANT_LAYERS = {
    6: ("hidro", "Hidroeléctrica SEIN"),
    9: (None, "Térmica SEIN"),
    12: (None, "Reserva fría"),
    17: ("hidro", "Hidroeléctrica no convencional"),
    18: ("eolica", "Eólica"),
    19: ("bioenergia", "Biomasa"),
    20: ("solar", "Solar"),
}


def _num(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


MAX_PLANT_MW = 3000.0  # the largest Peruvian plant (Mantaro) is about 1,000 MW


def _mw(value: Any) -> float | None:
    """POT_INST is in MW, except four records typed in kW (Huanza reads 98,316): above the
    largest plausible plant the value is read as kW."""
    mw = _num(value)
    if mw is not None and mw > MAX_PLANT_MW:
        return mw / 1000
    return mw


class OsinergminPeruSource:
    country = "PER"

    def __init__(self, http: CachedHttp, base_url: str) -> None:
        self.http = http
        self.base = base_url

    def _layer(self, layer: int, refresh: bool) -> list[dict[str, Any]]:
        return query_layer(self.http, f"{self.base}/{layer}", f"regional/per/gisem_{layer}.geojson", refresh)

    def fetch(self, refresh: bool = False) -> RegionalBundle:
        bundle = RegionalBundle(self.country, "Perú")
        bundle.sources.append(
            RegionalSource(
                id="osinergmin_gisem",
                name="Osinergmin GISEM, mapa del SEIN en operación",
                publisher="Osinergmin, Perú",
                url=self.base,
                license="No declarada; datos públicos del gobierno de Perú",
                attribution="Osinergmin GISEM",
                provides=("lines", "substations", "plants"),
                fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        )
        for layer, nominal in LINE_LAYERS.items():
            for f in self._layer(layer, refresh):
                p, g = f["properties"], f.get("geometry")
                if not g or not g.get("coordinates"):
                    continue
                parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
                levels = parse_kv_levels(p.get("TENSION_NOM")) or [float(nominal)]
                a, b = (p.get("NODO_SALIDA") or "").strip(), (p.get("NODO_LLEGADA") or "").strip()
                name = (p.get("NOMBRE") or f"{a} - {b}").strip()
                for part in parts:
                    if len(part) < 2:
                        continue
                    bundle.lines.append(
                        RegionalLine(
                            record=str(p["OBJECTID"]),
                            name=name,
                            kv=levels[0],
                            kv_levels=levels,
                            coords=[(float(c[0]), float(c[1])) for c in part],
                            source=f"Osinergmin GISEM capa {layer}",
                            circuits=int(p["NRO_TERNAS"]) if _num(p.get("NRO_TERNAS")) else None,
                            length_km=_num(p.get("LONGITUD")),
                            status=(p.get("ESTADO") or "").strip() or None,
                        )
                    )
        for layer, nominal in SUBSTATION_LAYERS.items():
            for f in self._layer(layer, refresh):
                p, g = f["properties"], f.get("geometry")
                if not g:
                    continue
                levels = parse_kv_levels(p.get("TENSION_NOM")) or [float(nominal)]
                bundle.substations.append(
                    RegionalSubstation(
                        record=str(p["OBJECTID"]),
                        name=(p.get("NOMBRE") or "").strip(),
                        kv=levels[0],
                        kv_levels=levels,
                        lon=float(g["coordinates"][0]),
                        lat=float(g["coordinates"][1]),
                        source=f"Osinergmin GISEM capa {layer}",
                    )
                )
        for layer, (tech, label) in PLANT_LAYERS.items():
            for f in self._layer(layer, refresh):
                p, g = f["properties"], f.get("geometry")
                if not g:
                    continue
                fuel = (p.get("FUENTE_ENER") or label).strip()
                bundle.plants.append(
                    RegionalPlant(
                        record=str(p["OBJECTID"]),
                        name=(p.get("NOMBRE") or "").strip(),
                        tech=tech or tech_from_text(fuel) or "termica",
                        mw=_mw(p.get("POT_INST")),
                        lon=float(g["coordinates"][0]),
                        lat=float(g["coordinates"][1]),
                        source=f"Osinergmin GISEM capa {layer}",
                        status=(p.get("ESTADO") or "").strip() or None,
                        fuel=fuel,
                    )
                )
        return bundle
