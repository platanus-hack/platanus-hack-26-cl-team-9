"""Adapter: EPE WebMap (Brazil), ArcGIS MapServer with existing lines, substations and plants."""

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
)
from cascadasen.infrastructure.arcgis import query_layer
from cascadasen.infrastructure.http import CachedHttp

LINES_LAYER = 23
SUBSTATIONS_LAYER = 22
PLANT_LAYERS = {
    14: ("eolica", "Eólica"),
    15: ("solar", "Solar fotovoltaica"),
    16: ("hidro", "Hidroeléctrica"),
    17: ("hidro", "Pequeña central hidroeléctrica"),
    18: ("hidro", "Central hidroeléctrica mínima"),
    19: ("bioenergia", "Biomasa"),
    20: ("termica", "Térmica fósil"),
    21: ("nuclear", "Nuclear"),
}


def _get(props: dict[str, Any], *names: str) -> Any:
    """EPE layers differ in the case of field names (Nome / NOME / nome)."""
    lower = {k.lower(): v for k, v in props.items()}
    for name in names:
        if lower.get(name.lower()) not in (None, ""):
            return lower[name.lower()]
    return None


def _kw_to_mw(value: Any) -> float | None:
    """The EPE layers give the installed power in kW (Itaipú reads 14,000,000)."""
    try:
        return float(value) / 1000 if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _parts(geometry: dict[str, Any] | None) -> list[list[tuple[float, float]]]:
    if not geometry or not geometry.get("coordinates"):
        return []
    raw = [geometry["coordinates"]] if geometry["type"] == "LineString" else geometry["coordinates"]
    return [[(float(c[0]), float(c[1])) for c in part] for part in raw if len(part) >= 2]


class EpeBrasilSource:
    country = "BRA"

    def __init__(self, http: CachedHttp, base_url: str) -> None:
        self.http = http
        self.base = base_url

    def _layer(self, layer: int, refresh: bool) -> list[dict[str, Any]]:
        return query_layer(
            self.http, f"{self.base}/{layer}", f"regional/bra/epe_{layer}.geojson", refresh, page_size=2000
        )

    def fetch(self, refresh: bool = False) -> RegionalBundle:
        src = "EPE WebMap"
        bundle = RegionalBundle(self.country, "Brasil")
        bundle.sources.append(
            RegionalSource(
                id="epe_webmap",
                name="EPE WebMap, sistema eléctrico existente",
                publisher="Empresa de Pesquisa Energética (EPE), Brasil",
                url=self.base,
                license="No declarada; datos públicos del gobierno de Brasil",
                attribution="EPE WebMap",
                provides=("lines", "substations", "plants"),
                fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
        )
        for f in self._layer(LINES_LAYER, refresh):
            p = f["properties"]
            levels = parse_kv_levels(_get(p, "Tensao"))
            for part in _parts(f.get("geometry")):
                bundle.lines.append(
                    RegionalLine(
                        record=str(p["OBJECTID"]),
                        name=str(_get(p, "Nome") or "").strip(),
                        kv=levels[0] if levels else None,
                        kv_levels=levels,
                        coords=part,
                        source=f"{src} capa {LINES_LAYER}",
                        length_km=_get(p, "Extensao"),
                        status="operación",
                    )
                )
        for f in self._layer(SUBSTATIONS_LAYER, refresh):
            p, g = f["properties"], f.get("geometry")
            if not g:
                continue
            levels = parse_kv_levels(_get(p, "Tensao"))
            bundle.substations.append(
                RegionalSubstation(
                    record=str(p["OBJECTID"]),
                    name=str(_get(p, "Nome") or "").strip(),
                    kv=levels[0] if levels else None,
                    kv_levels=levels,
                    lon=float(g["coordinates"][0]),
                    lat=float(g["coordinates"][1]),
                    source=f"{src} capa {SUBSTATIONS_LAYER}",
                )
            )
        for layer, (tech, label) in PLANT_LAYERS.items():
            for f in self._layer(layer, refresh):
                p, g = f["properties"], f.get("geometry")
                if not g:
                    continue
                bundle.plants.append(
                    RegionalPlant(
                        record=str(p["OBJECTID"]),
                        name=str(_get(p, "nome") or "").strip(),
                        tech=tech,
                        mw=_kw_to_mw(_get(p, "potencia")),
                        lon=float(g["coordinates"][0]),
                        lat=float(g["coordinates"][1]),
                        source=f"{src} capa {layer}",
                        status="operación",
                        fuel=str(_get(p, "combust") or label),
                    )
                )
        return bundle
