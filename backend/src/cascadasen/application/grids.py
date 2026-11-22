"""Grids as documents (docs/grids.md): publish `data/processed` to a store, list it and compose a grid.

Why: the user builds the grid they want to see from the documents the backend offers, edits it in the
browser and keeps it there. Publishing converts the raw files into the shape the app reads, once; composing
only picks and joins those documents, so a request never runs the engine or reads the raw snapshot.
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


def plan_workflow(processed: Path, scenarios_dir: Path) -> list[layout.GridFile]:
    """Every document to publish: the app-ready ones first, then the raw sources they come from."""
    snapshot, ops, base = (
        _read(processed / n) for n in ("grid_snapshot.json", "operating_points.json", "baseline_opf.json")
    )
    return [
        *_chile_documents(snapshot, ops, base),
        *_regional_documents(processed),
        *_scenario_documents(scenarios_dir),
        *layout.source_files(processed, _split_outlines(processed)),
    ]


def publish_workflow(
    store: GridStore,
    processed: Path,
    scenarios_dir: Path,
    built_at: str | None = None,
    commit: str = "unknown",
) -> dict:
    files = plan_workflow(processed, scenarios_dir)
    manifest = layout.build_manifest(files, _countries(processed), built_at or _now(), commit)
    for f in files:
        store.write(f.key, f.read())
    store.write(layout.MANIFEST, _encode(manifest))  # last: a catalogue never points at missing files
    return manifest


def verify_workflow(store: GridStore) -> list[str]:
    return layout.check_manifest(_manifest(store), store.read)


def catalog_workflow(store: GridStore) -> dict:
    manifest = _manifest(store)
    by_role = {role: [f for f in manifest["files"] if f["role"] == role] for role in layout.ROLES}
    return {
        "built_at": manifest["built_at"],
        "countries": manifest["countries"],
        "points": [{"key": f["key"], **f["meta"]} for f in by_role["operating"]],
        "scenarios": [f["meta"] for f in by_role["scenario"]],
        "context": [{k: f[k] for k in ("key", "country", "bytes")} | f["meta"] for f in by_role["context"]],
        "documents": [f for f in manifest["files"] if f["role"] != "source"],
    }


# ---- compose ----------------------------------------------------------------------------------


class GridComposer:
    """Joins the stored documents the user picked into one grid. Parsed documents are cached by checksum."""

    def __init__(self, store: GridStore) -> None:
        self.store = store
        self._parsed: dict[str, dict] = {}

    def compose_workflow(
        self, point: str | None = None, scenario: str | None = None, context: list[str] | None = None
    ) -> dict:
        """`context`: the context documents to include (None: all of them, [] none)."""
        manifest = _manifest(self.store)
        chosen = self._scenario(manifest, scenario) if scenario else {"point": point}
        operating = self._doc(
            manifest, layout.operating_key(_require_point(chosen.get("point"))), "el punto de operación"
        )
        network = self._doc(manifest, layout.network_key(operating["year"]), "la red")
        _check_fit(network, operating)
        return {
            "schema": layout.SCHEMA,
            "country": layout.TOPOLOGY_COUNTRY,
            "point": operating["point"],
            "label": operating["label"],
            "year": operating["year"],
            "scenario": chosen.get("id"),
            "built_at": manifest["built_at"],
            "sources": [
                _ref(manifest, layout.network_key(operating["year"])),
                _ref(manifest, layout.operating_key(operating["point"])),
            ],
            "network": {"nodes": network["nodes"], "lines": network["lines"]},
            "operating": operating["buses"],
            "open_lines": chosen.get("open_lines", []),
            "overlay": chosen.get("overlay", {}),  # applied by the simulator, not by compose (docs/grids.md)
            "context": _context_keys(manifest, context),
        }

    def document_workflow(self, key: str) -> bytes:
        """One context document as stored, checked against the catalogue."""
        manifest = _manifest(self.store)
        entry = next((f for f in manifest["files"] if f["key"] == key and f["role"] == "context"), None)
        if entry is None:
            raise GridError("not_found", f"No existe el documento de contexto: {key}")
        data = self.store.read(key)
        if data is None or layout.sha256(data) != entry["sha256"]:
            raise GridError("unavailable", f"{key} no coincide con el catálogo")
        return data

    def _scenario(self, manifest: dict, scenario_id: str) -> dict:
        return self._doc(manifest, f"scenarios/{scenario_id}.json", "el escenario")

    def _doc(self, manifest: dict, key: str, what: str) -> dict:
        entry = next((f for f in manifest["files"] if f["key"] == key), None)
        if entry is None:
            raise GridError("not_found", f"No existe {what}: {key}")
        if entry["sha256"] not in self._parsed:
            data = self.store.read(key)
            if data is None or layout.sha256(data) != entry["sha256"]:
                raise GridError("unavailable", f"{key} no coincide con el catálogo")
            self._parsed[entry["sha256"]] = json.loads(data)
        return self._parsed[entry["sha256"]]


def _check_fit(network: dict, operating: dict) -> None:
    """A network and an operating point fit when they cover the same buses (docs/grids.md)."""
    ids = {n["id"] for n in network["nodes"]}
    if ids != set(operating["buses"]) or network["year"] != operating["year"]:
        raise GridError("invalid", "La red y el punto de operación no corresponden a las mismas barras")


def _ref(manifest: dict, key: str) -> dict:
    return {"key": key, "sha256": next(f["sha256"] for f in manifest["files"] if f["key"] == key)}


def _context_keys(manifest: dict, wanted: list[str] | None) -> list[str]:
    known = [f["key"] for f in manifest["files"] if f["role"] == "context"]
    unknown = [k for k in wanted or [] if k not in known]
    if unknown:
        raise GridError("invalid", f"No son documentos de contexto: {', '.join(unknown)}")
    return known if wanted is None else list(dict.fromkeys(wanted))


def _require_point(point: str | None) -> str:
    if not point:
        raise GridError("invalid", "Indica un punto de operación o un escenario")
    return point


# ---- documents built at publish time ----------------------------------------------------------


def _chile_documents(snapshot: dict, ops: dict, base: dict) -> list[layout.GridFile]:
    country = layout.TOPOLOGY_COUNTRY
    points = ops["points"]
    nets = {y: reduce_network(snapshot, y) for y in sorted({int(p["snapshot"][:4]) for p in points})}
    files = [
        layout.GridFile(
            layout.network_key(y),
            country,
            "network",
            data=_encode({"schema": layout.SCHEMA, "country": country, "year": y, **network_json(net)}),
            meta={"year": y},
        )
        for y, net in nets.items()
    ]
    for p in points:
        year = int(p["snapshot"][:4])
        net = nets[year]
        op = operating_point_from_docs(net, ops, base, snapshot, p["id"])
        meta = {"point": p["id"], "label": op.label, "year": year, "snapshot": p["snapshot"]}
        buses = {
            f"B{i:03d}": {
                "gen_mw": round(float(op.gen[i]), 1),
                "load_mw": round(float(op.load[i]), 1),
                "sync_mw": round(float(op.sync_mw[i]), 1),
                "inertia_mws": round(float(op.inertia_mws[i]), 1),
                "people": round(float(op.people[i])),
            }
            for i in range(net.size)
        }
        files.append(
            layout.GridFile(
                layout.operating_key(p["id"]),
                country,
                "operating",
                data=_encode({"schema": layout.SCHEMA, "country": country, **meta, "buses": buses}),
                meta=meta,
            )
        )
    return files


def _regional_documents(processed: Path) -> list[layout.GridFile]:
    files = []
    for iso, meta in _countries(processed).items():
        parts = [
            _read(processed / "latam" / iso / f"{layer}.geojson")
            for layer in ("lines", "substations", "plants")
        ]
        doc = layout.regional_document(iso, meta, *parts)
        info = {
            "name": meta.get("name", iso),
            "lines": len(doc["lines"]),
            "substations": len(doc["substations"]),
            "plants": len(doc["plants"]),
        }
        files.append(layout.GridFile(layout.country_key(iso), iso, "context", data=_encode(doc), meta=info))
    return files


def _scenario_documents(folder: Path) -> list[layout.GridFile]:
    files = []
    for path in sorted(folder.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        meta = {k: doc.get(k) for k in ("id", "name", "point", "open_lines")} | {
            "edits": bool(doc.get("overlay"))
        }
        files.append(
            layout.GridFile(
                f"scenarios/{path.name}", layout.TOPOLOGY_COUNTRY, "scenario", source=path, meta=meta
            )
        )
    return files


# ---- helpers ----------------------------------------------------------------------------------


def _manifest(store: GridStore) -> dict:
    data = store.read(layout.MANIFEST)
    if data is None:
        raise GridError("unavailable", "No hay catálogo de grillas publicado (cascadasen-grids publish)")
    return json.loads(data)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _split_outlines(processed: Path) -> dict[str, bytes]:
    path = processed / "latam" / "outlines.geojson"
    if not path.is_file():
        return {}
    doc = _read(path)
    return {f["properties"]["shapeGroup"]: _encode({**doc, "features": [f]}) for f in doc["features"]}


def _countries(processed: Path) -> dict:
    path = processed / "latam" / "manifest.json"
    return _read(path)["countries"] if path.is_file() else {}


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
    parser.add_argument("--out", type=Path, default=settings.grids_dir, help="carpeta del store local")
    parser.add_argument("--bucket", default=settings.grids_bucket or settings.session_bucket)
    parser.add_argument("--prefix", default=settings.grids_prefix)
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
    files = plan_workflow(processed, scenarios)
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
