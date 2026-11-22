"""Layout of the grid documents (docs/grids.md): which document lives under which key.

Why: a grid is a set of JSON documents organised by country, already in the shape the app reads, so that
composing a grid only picks and joins them. The raw files of `data/processed` stay next to them as `source`
for traceability. Nothing here touches disk or S3: layout, conversions, manifest and checksums are pure.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "cascadasen.grid/2"
MANIFEST = "manifest.json"
TOPOLOGY_COUNTRY = "CHL"  # the only country with a simulable network (docs/grids.md)
LATAM = ("ARG", "BOL", "BRA", "PER")
LAYERS = ("substations", "taps", "lines", "plants", "storage", "comunas")
ROLES = ("network", "operating", "context", "scenario", "source")

# raw file under data/processed -> key under CHL/source
_CHILE_SOURCES = (
    "grid_snapshot.json",
    "comunas_geometry.json",
    "node_index.json",
    "sen_network.json",
    "operating_points.json",
    "baseline_opf.json",
    "chile.geojson",
    *(f"geo/{n}.geojson" for n in LAYERS),
)


@dataclass(frozen=True)
class GridFile:
    key: str  # relative to the prefix, e.g. "CHL/network-2025.json"
    country: str
    role: str
    source: Path | None = None  # file to publish; None when `data` is given
    data: bytes | None = None
    meta: dict = field(default_factory=dict)  # small facts the catalogue shows without reading the document

    def read(self) -> bytes:
        return self.data if self.data is not None else self.source.read_bytes()  # type: ignore[union-attr]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def network_key(year: int) -> str:
    return f"{TOPOLOGY_COUNTRY}/network-{year}.json"


def operating_key(point_id: str) -> str:
    return f"{TOPOLOGY_COUNTRY}/operating/{point_id}.json"


def country_key(iso: str) -> str:
    return f"{iso}/grid.json"


def source_files(processed: Path, outlines: dict[str, bytes]) -> list[GridFile]:
    """The raw files, kept as `source` under each country. `outlines` are the per-country slices of latam/outlines."""
    files = [
        GridFile(f"{TOPOLOGY_COUNTRY}/source/{name}", TOPOLOGY_COUNTRY, "source", source=processed / name)
        for name in _CHILE_SOURCES
        if (processed / name).is_file()
    ]
    for iso in LATAM:
        for layer in ("lines", "substations", "plants"):
            path = processed / "latam" / iso / f"{layer}.geojson"
            if path.is_file():
                files.append(GridFile(f"{iso}/source/{layer}.geojson", iso, "source", source=path))
        if iso in outlines:
            files.append(GridFile(f"{iso}/source/outline.geojson", iso, "source", data=outlines[iso]))
    return files


def regional_document(iso: str, meta: dict, lines: dict, substations: dict, plants: dict) -> dict:
    """One country of context in the shape the web draws (web/src/map/regional.ts `RegionalGrid`, one country)."""

    def props(f: dict) -> dict:
        return f["properties"]

    return {
        "schema": SCHEMA,
        "country": iso,
        "meta": {"country": iso, **meta},  # name, counts, raw_counts, plant_count, sources, warnings
        "lines": [
            {
                "id": props(f)["id"],
                "kv": props(f)["kv"],
                "circuits": props(f)["circuits"],
                "lengthKm": props(f)["length_km"],
                "source": props(f)["source"],
                "path": f["geometry"]["coordinates"],
            }
            for f in lines["features"]
        ],
        "substations": [
            {
                "id": props(f)["id"],
                "name": props(f)["name"],
                "kv": props(f)["kv"],
                "kind": props(f)["kind"],
                "source": props(f)["source"],
                "position": f["geometry"]["coordinates"],
            }
            for f in substations["features"]
        ],
        "plants": [
            {
                "id": props(f)["id"],
                "name": props(f)["name"],
                "tech": props(f)["tech"],
                "mw": props(f)["mw"],
                "count": props(f)["count"],
                "source": props(f)["source"],
                "position": f["geometry"]["coordinates"],
            }
            for f in plants["features"]
        ],
    }


def build_manifest(files: list[GridFile], countries: dict, built_at: str, commit: str) -> dict:
    return {
        "schema": SCHEMA,
        "built_at": built_at,
        "commit": commit,
        "countries": countries,  # name, counts, sources, licence and warnings, from latam/manifest.json
        "files": [
            {
                "key": f.key,
                "country": f.country,
                "role": f.role,
                "bytes": len(f.read()),
                "sha256": sha256(f.read()),
                **({"meta": f.meta} if f.meta else {}),
            }
            for f in files
        ],
    }


def check_manifest(manifest: dict, read) -> list[str]:
    """Problems found: files missing from the store or whose bytes differ from the manifest."""
    problems = []
    for entry in manifest["files"]:
        data = read(entry["key"])
        if data is None:
            problems.append(f"falta {entry['key']}")
        elif sha256(data) != entry["sha256"]:
            problems.append(f"sha256 distinto en {entry['key']}")
    return problems
