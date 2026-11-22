"""Layout of the grid documents (docs/grids.md): which file of `data/processed` becomes which key.

Why: a grid is a set of JSON documents organised by country. The backend composes the ones the user
picks into one grid document that the browser keeps locally. Nothing here touches disk or S3: the
layout, the manifest and the checksums are pure so that any store can publish and verify them.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

SCHEMA = "cascadasen.grid/1"
MANIFEST = "manifest.json"
TOPOLOGY_COUNTRY = "CHL"  # the only country with a simulable topology (docs/grids.md)
LATAM = ("ARG", "BOL", "BRA", "PER")
LAYERS = ("substations", "taps", "lines", "plants", "storage", "comunas")

# (file under data/processed, key under the prefix, role). Role: topology | operating | context
_CHILE = (
    ("grid_snapshot.json", "grid_snapshot.json", "topology"),
    ("comunas_geometry.json", "comunas_geometry.json", "topology"),
    ("node_index.json", "node_index.json", "topology"),
    ("sen_network.json", "sen_network.json", "topology"),
    ("operating_points.json", "operating_points.json", "operating"),
    ("baseline_opf.json", "baseline_opf.json", "operating"),
    ("chile.geojson", "outline.geojson", "context"),
    *((f"geo/{n}.geojson", f"geo/{n}.geojson", "context") for n in LAYERS),
)


@dataclass(frozen=True)
class GridFile:
    key: str  # relative to the prefix, e.g. "CHL/grid_snapshot.json"
    country: str
    role: str
    source: Path | None = None  # file to publish; None when `data` is given
    data: bytes | None = None

    def read(self) -> bytes:
        return self.data if self.data is not None else self.source.read_bytes()  # type: ignore[union-attr]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plan(processed: Path, scenarios: list[tuple[str, bytes]], outlines: dict[str, bytes]) -> list[GridFile]:
    """Every file to publish. `outlines` are the per-country slices of latam/outlines.geojson."""
    files = [
        GridFile(f"{TOPOLOGY_COUNTRY}/{key}", TOPOLOGY_COUNTRY, role, source=processed / src)
        for src, key, role in _CHILE
        if (processed / src).is_file()
    ]
    for iso in LATAM:
        for layer in ("lines", "substations", "plants"):
            path = processed / "latam" / iso / f"{layer}.geojson"
            if path.is_file():
                files.append(GridFile(f"{iso}/{layer}.geojson", iso, "context", source=path))
        if iso in outlines:
            files.append(GridFile(f"{iso}/outline.geojson", iso, "context", data=outlines[iso]))
    files += [GridFile(f"scenarios/{name}", "CHL", "scenario", data=data) for name, data in scenarios]
    return files


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
