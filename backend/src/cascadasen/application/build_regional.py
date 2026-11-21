"""cascadasen-regional: build the regional context layer (docs/regional.md).

One GeoJSON file per country and layer under data/processed/latam/<ISO3>/, plus a manifest with
counts, kilometres per voltage and the sources (and licences) of every country.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cascadasen.domain.ports import RegionalGridSource
from cascadasen.domain.regional import normalise
from cascadasen.domain.regional_reduction import feature_collections, manifest_entry, reduce_bundle

log = logging.getLogger(__name__)
LAYERS = ("lines", "substations", "plants")


class BuildRegionalGrid:
    def __init__(self, sources: dict[str, RegionalGridSource], out_dir: Path) -> None:
        self.sources = sources
        self.out_dir = out_dir

    def _manifest(self) -> dict[str, Any]:
        path = self.out_dir / "manifest.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {"version": 1, "countries": {}}

    def execute(self, countries: list[str], refresh: bool = False) -> tuple[dict[str, Any], dict[str, str]]:
        """Build the given countries. A failing source does not stop the others: it is returned in `errors`."""
        manifest, errors = self._manifest(), {}
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
            manifest["countries"][iso] = manifest_entry(reduced)
        manifest["built_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        manifest["countries"] = dict(sorted(manifest["countries"].items()))
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        return manifest, errors


def main() -> int:
    from cascadasen.infrastructure.container import DEFAULT_COUNTRIES, regional_use_case
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
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
