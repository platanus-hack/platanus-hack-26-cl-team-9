"""Grids as documents (docs/grids.md): publish `data/processed` to a store, list it and compose a grid.

Why: the user builds the grid they want to see from the documents the backend offers, edits it in the
browser and keeps it there. The backend only reads documents and composes; it keeps no session for this.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from cascadasen.application.cache_builder import network_json
from cascadasen.domain import grids as layout
from cascadasen.domain.cascade.network import reduce_network
from cascadasen.domain.cascade.scenario import operating_point_from_docs
from cascadasen.domain.ports import GridStore


class GridError(Exception):
    """`kind`: not_found (unknown id), invalid (documents that do not fit together), unavailable (no catalogue)."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


# ---- publish / verify -------------------------------------------------------------------------


def publish_workflow(
    store: GridStore,
    processed: Path,
    scenarios_dir: Path,
    built_at: str | None = None,
    commit: str = "unknown",
) -> dict:
    files = layout.plan(processed, _read_scenarios(scenarios_dir), _split_outlines(processed))
    manifest = layout.build_manifest(files, _countries(processed), built_at or _now(), commit)
    for f in files:
        store.write(f.key, f.read())
    store.write(layout.MANIFEST, _encode(manifest))  # last: a catalogue never points at missing files
    return manifest


def verify_workflow(store: GridStore) -> list[str]:
    manifest = _manifest(store)
    return layout.check_manifest(manifest, store.read)


def catalog_workflow(store: GridStore) -> dict:
    manifest = _manifest(store)
    scenarios = [_scenario_summary(store, f["key"]) for f in manifest["files"] if f["role"] == "scenario"]
    return {
        "built_at": manifest["built_at"],
        "countries": manifest["countries"],
        "documents": [f for f in manifest["files"] if f["role"] != "scenario"],
        "scenarios": scenarios,
    }


# ---- compose ----------------------------------------------------------------------------------


class GridComposer:
    """Builds a grid document from the stored sources. Parsed documents are cached by checksum."""

    def __init__(self, store: GridStore) -> None:
        self.store = store
        self._parsed: dict[str, dict] = {}

    def compose_workflow(self, point: str | None = None, scenario: str | None = None) -> dict:
        manifest = _manifest(self.store)
        chosen = self._scenario(manifest, scenario) if scenario else {"point": point}
        point_id = _require_point(chosen.get("point"))
        topology, ops, base = (self._doc(manifest, name) for name in layout_names())
        year = _point_year(ops, point_id)
        net = reduce_network(topology, year)
        op = operating_point_from_docs(net, ops, base, topology, point_id)
        return _grid_document(manifest, chosen, point_id, year, net, op)

    def _scenario(self, manifest: dict, scenario_id: str) -> dict:
        key = f"scenarios/{scenario_id}.json"
        if key not in {f["key"] for f in manifest["files"]}:
            raise GridError("not_found", f"No existe el escenario: {scenario_id}")
        return self._doc(manifest, key, absolute=True)

    def _doc(self, manifest: dict, name: str, absolute: bool = False) -> dict:
        key = name if absolute else f"{layout.TOPOLOGY_COUNTRY}/{name}"
        entry = next((f for f in manifest["files"] if f["key"] == key), None)
        if entry is None:
            raise GridError("unavailable", f"El catálogo no tiene {key}")
        if entry["sha256"] not in self._parsed:
            data = self.store.read(key)
            if data is None or layout.sha256(data) != entry["sha256"]:
                raise GridError("unavailable", f"{key} no coincide con el catálogo")
            self._parsed[entry["sha256"]] = json.loads(data)
        return self._parsed[entry["sha256"]]


def layout_names() -> tuple[str, str, str]:
    return "grid_snapshot.json", "operating_points.json", "baseline_opf.json"


def _grid_document(manifest: dict, chosen: dict, point_id: str, year: int, net, op) -> dict:
    ids = [f"B{i:03d}" for i in range(net.size)]
    sources = [
        f for f in manifest["files"] if f["country"] == layout.TOPOLOGY_COUNTRY and f["role"] != "scenario"
    ]
    return {
        "schema": layout.SCHEMA,
        "country": layout.TOPOLOGY_COUNTRY,
        "point": point_id,
        "label": op.label,
        "year": year,
        "scenario": chosen.get("id"),
        "built_at": manifest["built_at"],
        "sources": [{"key": f["key"], "sha256": f["sha256"]} for f in sources if f["role"] != "context"],
        "network": network_json(net),
        "operating": {
            ids[i]: {
                "gen_mw": round(float(op.gen[i]), 1),
                "load_mw": round(float(op.load[i]), 1),
                "sync_mw": round(float(op.sync_mw[i]), 1),
                "inertia_mws": round(float(op.inertia_mws[i]), 1),
                "people": round(float(op.people[i])),
            }
            for i in range(net.size)
        },
        "open_lines": chosen.get("open_lines", []),
        "overlay": chosen.get("overlay", {}),  # applied by the simulator, not by compose (docs/grids.md)
        "context": [f["key"] for f in sources if f["role"] == "context"],
    }


def _require_point(point: str | None) -> str:
    if not point:
        raise GridError("invalid", "Indica un punto de operación o un escenario")
    return point


def _point_year(ops: dict, point_id: str) -> int:
    found = next((p for p in ops["points"] if p["id"] == point_id), None)
    if found is None:
        raise GridError("not_found", f"No existe el punto de operación: {point_id}")
    return int(found["snapshot"][:4])


# ---- helpers ----------------------------------------------------------------------------------


def _manifest(store: GridStore) -> dict:
    data = store.read(layout.MANIFEST)
    if data is None:
        raise GridError("unavailable", "No hay catálogo de grillas publicado (cascadasen-grids publish)")
    return json.loads(data)


def _scenario_summary(store: GridStore, key: str) -> dict:
    doc = json.loads(store.read(key) or b"{}")
    return {k: doc.get(k) for k in ("id", "name", "point", "open_lines")} | {
        "edits": bool(doc.get("overlay"))
    }


def _read_scenarios(folder: Path) -> list[tuple[str, bytes]]:
    return [(p.name, p.read_bytes()) for p in sorted(folder.glob("*.json"))]


def _split_outlines(processed: Path) -> dict[str, bytes]:
    path = processed / "latam" / "outlines.geojson"
    if not path.is_file():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {f["properties"]["shapeGroup"]: _encode({**doc, "features": [f]}) for f in doc["features"]}


def _countries(processed: Path) -> dict:
    path = processed / "latam" / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))["countries"] if path.is_file() else {}


def _encode(doc: dict) -> bytes:
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_commit(root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# ---- CLI --------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    from cascadasen.infrastructure.grid_store import LocalGridStore, S3GridStore
    from cascadasen.infrastructure.settings import REPO_ROOT, get_settings

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Publica, verifica y lista los documentos de grillas.")
    parser.add_argument("action", choices=["publish", "verify", "list"])
    parser.add_argument("--store", choices=["local", "s3"], default="local")
    parser.add_argument(
        "--out", type=Path, default=settings.data_dir / "grids", help="carpeta del store local"
    )
    parser.add_argument("--bucket", default=settings.session_bucket)
    parser.add_argument("--prefix", default="grids/v1")
    parser.add_argument("--region", default=settings.aws_region)
    parser.add_argument("--profile", default=settings.aws_profile)
    parser.add_argument("--dry-run", action="store_true", help="solo muestra qué se publicaría")
    parser.add_argument("--yes", action="store_true", help="confirma la escritura en S3")
    args = parser.parse_args(argv)

    if args.store == "s3":
        if not args.bucket:
            parser.error("--bucket es obligatorio con --store s3")
        store: GridStore = S3GridStore(args.bucket, args.prefix, args.region, args.profile)
    else:
        store = LocalGridStore(args.out)

    if args.action == "verify":
        problems = verify_workflow(store)
        print("\n".join(problems) or "OK: todos los documentos coinciden con el catálogo")
        return 1 if problems else 0
    if args.action == "list":
        print("\n".join(store.keys()))
        return 0

    processed, scenarios = settings.processed_dir, settings.data_dir / "scenarios"
    files = layout.plan(processed, _read_scenarios(scenarios), _split_outlines(processed))
    total = sum(len(f.read()) for f in files)
    print(
        f"{len(files)} documentos, {total / 1e6:.1f} MB -> {args.store}:{args.prefix if args.store == 's3' else args.out}"
    )
    if args.dry_run:
        print("\n".join(f"  {f.role:9} {f.key}" for f in files))
        return 0
    if args.store == "s3" and not args.yes:
        print("Falta --yes para escribir en S3", file=sys.stderr)
        return 2
    if store.keys():
        print("El destino no está vacío: no se sobrescribe nada", file=sys.stderr)
        return 2
    publish_workflow(store, processed, scenarios, commit=_git_commit(REPO_ROOT))
    print("publicado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
