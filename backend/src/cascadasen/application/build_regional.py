"""cascadasen-regional: build the regional context layer (docs/regional.md).

One GeoJSON file per country and layer under data/processed/latam/<ISO3>/, plus a manifest with
counts, kilometres per voltage and the sources (and licences) of every country. With `--ons`, also
Brazil's flow network from the ONS datasets (`BRA/network.json`, docs/network-format.md).
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cascadasen.domain.ports import FlowNetworkSource, RegionalGridSource
from cascadasen.domain.regional import normalise
from cascadasen.domain.regional_network import (
    build_flow_network,
    deduction_error,
    flow_manifest_entry,
    network_document,
)
from cascadasen.domain.regional_reduction import feature_collections, manifest_entry, reduce_bundle
from cascadasen.domain.simulation.params import load_params, value
from cascadasen.domain.validation import X_PER_KM

log = logging.getLogger(__name__)
LAYERS = ("lines", "substations", "plants")


def _read_manifest(out_dir: Path) -> dict[str, Any]:
    path = out_dir / "manifest.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"version": 1, "countries": {}}


def _write_manifest(out_dir: Path, manifest: dict[str, Any]) -> None:
    manifest["built_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    manifest["countries"] = dict(sorted(manifest["countries"].items()))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
    )


class BuildRegionalGrid:
    def __init__(self, sources: dict[str, RegionalGridSource], out_dir: Path) -> None:
        self.sources = sources
        self.out_dir = out_dir

    def execute(self, countries: list[str], refresh: bool = False) -> tuple[dict[str, Any], dict[str, str]]:
        """Build the given countries. A failing source does not stop the others: it is returned in `errors`."""
        manifest, errors = _read_manifest(self.out_dir), {}
        for iso in countries:
            source = self.sources.get(iso)
            if source is None:
                errors[iso] = f"país sin fuente registrada (disponibles: {', '.join(sorted(self.sources))})"
                continue
            try:
                reduced = reduce_bundle(normalise(source.fetch(refresh=refresh)))
            except Exception as exc:
                log.exception("%s failed", iso)
                errors[iso] = str(exc)
                continue
            if not reduced.links:
                errors[iso] = "sin líneas tras filtrar: no se escribe el país"
                continue
            folder = self.out_dir / iso
            folder.mkdir(parents=True, exist_ok=True)
            for layer, collection in feature_collections(reduced).items():
                (folder / f"{layer}.geojson").write_text(
                    json.dumps(collection, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
                )
            entry = manifest_entry(reduced)
            if "flow" in manifest["countries"].get(iso, {}):  # built by BuildFlowNetwork, keep it
                entry["flow"] = manifest["countries"][iso]["flow"]
            manifest["countries"][iso] = entry
        _write_manifest(self.out_dir, manifest)
        return manifest, errors


class BuildFlowNetwork:
    """Flow network of one country from declared line ends and parameters (docs/network-format.md).

    The drawn layer's source of the same country gives the plants, the coordinate fallback by name and
    the distance-snapped topology that `deduction_error` compares with the declared one.
    """

    def __init__(self, source: FlowNetworkSource, drawn: RegionalGridSource, out_dir: Path) -> None:
        self.source = source
        self.drawn = drawn
        self.out_dir = out_dir

    def execute(self, refresh: bool = False, as_of: str | None = None) -> dict[str, Any]:
        iso = self.source.country
        built_at = datetime.now(UTC).isoformat(timespec="seconds")
        as_of = as_of or built_at[:10]
        drawn = normalise(self.drawn.fetch(refresh=refresh))
        net = build_flow_network(
            self.source.fetch(refresh=refresh), drawn.substations, drawn.plants, as_of, iso
        )
        typical_mva = {float(k): v for k, v in value(load_params("network")["typical_capacity_mva"]).items()}
        x_ranges = {float(k): v for k, v in X_PER_KM.items()}
        entry = flow_manifest_entry(net, built_at)
        entry["deduction_error"] = deduction_error(net, reduce_bundle(drawn), x_ranges, typical_mva)
        doc = network_document(net, built_at)
        doc["deduction_error"] = entry["deduction_error"]
        folder = self.out_dir / iso
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "network.json").write_text(
            json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        manifest = _read_manifest(self.out_dir)
        manifest["countries"].setdefault(iso, {"country": iso})["flow"] = entry
        _write_manifest(self.out_dir, manifest)
        return entry


def main() -> int:
    from cascadasen.infrastructure.container import (
        DEFAULT_COUNTRIES,
        flow_network_use_case,
        regional_use_case,
    )
    from cascadasen.infrastructure.settings import get_settings

    parser = argparse.ArgumentParser(
        description="Construye la capa de contexto de otras redes de Latinoamérica."
    )
    parser.add_argument(
        "--countries", default=",".join(DEFAULT_COUNTRIES), help="códigos ISO3 separados por coma"
    )
    parser.add_argument(
        "--osm", default="", help="países a leer de OpenStreetMap en vez de su fuente oficial"
    )
    parser.add_argument(
        "--ons",
        action="store_true",
        help="construye además la red de flujo de Brasil con los datos del ONS (BRA/network.json)",
    )
    parser.add_argument("--refresh", action="store_true", help="vuelve a descargar las fuentes")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s"
    )
    countries = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
    osm = {c.strip().upper() for c in args.osm.split(",") if c.strip()}
    manifest, errors = regional_use_case(get_settings(), osm=osm).execute(countries, refresh=args.refresh)
    for iso in countries:
        if iso in errors:
            print(f"{iso}: ERROR {errors[iso]}")
            continue
        e = manifest["countries"][iso]
        print(f"{iso}: {e['counts']} (antes {e['raw_counts']}) km por kV {e['line_km_by_kv']}")
        for w in e["warnings"]:
            print(f"    aviso: {w}")
    if args.ons:
        if "BRA" not in countries:
            print("--ons construye solo Brasil: agrega BRA a --countries")
            return 1
        try:
            flow = flow_network_use_case(get_settings()).execute(refresh=args.refresh)
        except Exception as exc:  # a failing source is reported, not raised, as for the drawn layer
            log.exception("BRA flow network failed")
            print(f"BRA red de flujo: ERROR {exc}")
            return 1
        _print_flow(flow)
    return 1 if errors else 0


def _print_flow(flow: dict[str, Any]) -> None:
    length, coords, err = flow["length_check"], flow["coordinates"], flow["deduction_error"]
    print(f"BRA red de flujo: {flow['counts']} -> {flow['file']}")
    print(f"    km de circuitos por kV {flow['circuit_km_by_kv']}")
    print(
        f"    largo CA {length['circuit_km_ac']:,.0f} km, CC {length['dc_km']:,.0f} km, "
        f"oficial {length['official_km']:,} km (CA {length['ac_vs_official']:+.1%}, "
        f"CA+CC {length['ac_dc_vs_official']:+.1%})"
    )
    print(f"    valores supuestos {flow['assumed']}; excluidas {flow['excluded']}")
    print(f"    coordenadas: {coords['match_rate']:.2%} de {coords['substations_needed']} subestaciones")
    print(
        f"    error de la red deducida: x mediana {err['x']['all'].get('median_abs')}, "
        f"capacidad mediana {err['capacity']['all'].get('median_abs')}, "
        f"topología precisión {err['topology'].get('precision')} recall {err['topology'].get('recall')}"
    )
    for w in flow["warnings"]:
        print(f"    aviso: {w}")


if __name__ == "__main__":
    raise SystemExit(main())
