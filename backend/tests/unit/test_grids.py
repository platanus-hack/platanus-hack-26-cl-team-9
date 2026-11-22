"""Grid documents: publish, verify, catalogue and compose (docs/grids.md)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.application.grids import (
    GridComposer,
    GridError,
    catalog_workflow,
    publish_workflow,
    verify_workflow,
)
from cascadasen.domain.ports import ConflictError
from cascadasen.infrastructure.grid_store import LocalGridStore, S3GridStore
from cascadasen.infrastructure.settings import REPO_ROOT, Settings

PROCESSED, SCENARIOS, CACHE = (
    REPO_ROOT / "data/processed",
    REPO_ROOT / "data/scenarios",
    REPO_ROOT / "web/public/cache",
)
pytestmark = pytest.mark.skipif(not (PROCESSED / "grid_snapshot.json").exists(), reason="no processed data")


@pytest.fixture(scope="module")
def store(tmp_path_factory) -> LocalGridStore:
    s = LocalGridStore(tmp_path_factory.mktemp("grids"))
    publish_workflow(s, PROCESSED, SCENARIOS, built_at="t", commit="test")
    return s


def test_publish_then_verify_and_never_overwrite(store):
    assert verify_workflow(store) == []
    with pytest.raises(ConflictError):
        store.write("manifest.json", b"{}")


def test_verify_reports_a_changed_document(tmp_path):
    s = LocalGridStore(tmp_path)
    publish_workflow(s, PROCESSED, SCENARIOS)
    (tmp_path / "CHL/source/baseline_opf.json").write_bytes(b"{}")
    assert verify_workflow(s) == ["sha256 distinto en CHL/source/baseline_opf.json"]


def test_catalog_lists_countries_documents_and_scenarios(store):
    cat = catalog_workflow(store)
    assert {c["country"] for c in cat["context"]} == {"ARG", "BOL", "BRA", "PER"}
    assert {p["point"] for p in cat["points"]} == {
        "feb2025-1500",
        "feb2025-0300",
        "nov2026-1300",
        "nov2026-2000",
    }
    assert all(d["role"] != "source" for d in cat["documents"])
    assert [(g["country"], g["status"]) for g in cat["grids"]] == [
        ("CHL", "Complete"),
        ("ARG", "Partial"),
        ("BOL", "Partial"),
        ("BRA", "Partial"),
        ("PER", "Partial"),
    ]
    assert {s["id"] for s in cat["scenarios"]} >= {"dia-normal", "25f"}
    assert next(s for s in cat["scenarios"] if s["id"] == "25f")["open_lines"] == ["R239"]


def test_compose_matches_the_precomputed_cache(store):
    grid = GridComposer(store).compose_workflow(point="feb2025-1500")
    cache = json.loads((CACHE / "network-2025.json").read_text())
    assert grid["network"]["lines"] == cache["lines"]
    assert [n["id"] for n in grid["network"]["nodes"]] == [n["id"] for n in cache["nodes"]]
    buses = json.loads((CACHE / "feb2025-1500/buses.json").read_text())
    assert {b: grid["operating"][b]["gen_mw"] for b in buses} == {b: v["gen_mw"] for b, v in buses.items()}
    assert grid["operating"]["B000"].keys() >= {"gen_mw", "load_mw", "sync_mw", "inertia_mws", "people"}


def test_compose_scenario_carries_its_cuts(store):
    grid = GridComposer(store).compose_workflow(scenario="25f")
    assert (grid["point"], grid["open_lines"], grid["scenario"]) == ("feb2025-1500", ["R239"], "25f")


@pytest.mark.parametrize(
    "kwargs, kind", [({"point": "nope"}, "not_found"), ({"scenario": "nope"}, "not_found"), ({}, "invalid")]
)
def test_compose_rejects_bad_requests(store, kwargs, kind):
    with pytest.raises(GridError) as exc:
        GridComposer(store).compose_workflow(**kwargs)
    assert exc.value.kind == kind


def test_compose_without_catalog_is_unavailable(tmp_path):
    with pytest.raises(GridError) as exc:
        GridComposer(LocalGridStore(tmp_path)).compose_workflow(point="feb2025-1500")
    assert exc.value.kind == "unavailable"


class _FakeS3:
    """Just enough of the boto3 client: put with IfNoneMatch, get, paginated list."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put_object(self, Bucket, Key, Body, ContentType, IfNoneMatch):
        from botocore.exceptions import ClientError

        if Key in self.objects:
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):
        from botocore.exceptions import ClientError

        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": type("B", (), {"read": lambda _s, d=self.objects[Key]: d})()}

    def get_paginator(self, _name):
        objects = self.objects
        return type(
            "P",
            (),
            {
                "paginate": lambda _s, Bucket, Prefix: [
                    {"Contents": [{"Key": k} for k in objects if k.startswith(Prefix)]}
                ]
            },
        )()


def test_s3_store_keeps_keys_under_the_prefix_and_never_overwrites():
    client = _FakeS3()
    s = S3GridStore("b", "grids/v1/", client=client)
    s.write("CHL/a.json", b"1")
    assert list(client.objects) == ["grids/v1/CHL/a.json"]
    assert s.read("CHL/a.json") == b"1" and s.read("missing") is None
    assert s.keys() == ["CHL/a.json"]
    with pytest.raises(ConflictError):
        s.write("CHL/a.json", b"2")


def test_api_compose_and_errors(tmp_path, store):
    app = create_app(settings=Settings(data_dir=tmp_path, grids_store="local"))
    client = TestClient(app)
    assert client.get("/api/v1/grids/sources").status_code == 503  # nothing published in tmp_path/grids
    app.state.grids = GridComposer(store)
    assert client.get("/api/v1/grids/scenarios").json()[0]["id"]
    ok = client.post("/api/v1/grids/compose", json={"scenario": "25f"})
    assert ok.status_code == 200 and ok.json()["open_lines"] == ["R239"]
    assert client.post("/api/v1/grids/compose", json={"point": "x"}).status_code == 404
    assert client.post("/api/v1/grids/compose", json={}).status_code == 422


def test_compose_context_selection_and_document(store):
    composer = GridComposer(store)
    assert composer.compose_workflow(point="feb2025-1500", context=[])["context"] == []
    pick = ["ARG/grid.json"]
    assert composer.compose_workflow(point="feb2025-1500", context=pick)["context"] == pick
    assert len(composer.compose_workflow(point="feb2025-1500")["context"]) == 4
    with pytest.raises(GridError) as exc:
        composer.compose_workflow(point="feb2025-1500", context=["CHL/network-2025.json"])
    assert exc.value.kind == "invalid"
    assert json.loads(composer.document_workflow("ARG/grid.json"))["lines"]
    with pytest.raises(GridError):
        composer.document_workflow("CHL/network-2025.json")


def test_regional_document_has_the_shape_the_web_draws(store):
    doc = json.loads(GridComposer(store).document_workflow("PER/grid.json"))
    assert doc["meta"]["country"] == "PER" and doc["meta"]["sources"]
    assert doc["lines"][0].keys() >= {"id", "kv", "circuits", "lengthKm", "source", "path"}
    assert doc["substations"][0].keys() >= {"id", "name", "kv", "kind", "source", "position"}
    assert doc["plants"][0].keys() >= {"id", "name", "tech", "mw", "count", "source", "position"}


def test_compose_rejects_a_network_that_does_not_fit_the_point(store):
    composer = GridComposer(store)
    other = composer.compose_workflow(point="nov2026-1300")["network"]
    manifest = json.loads(store.read("manifest.json"))
    composer._parsed[next(f["sha256"] for f in manifest["files"] if f["key"] == "CHL/network-2025.json")] = {
        "year": 2025,
        "nodes": other["nodes"][:-1],
        "lines": [],
    }
    with pytest.raises(GridError) as exc:
        composer.compose_workflow(point="feb2025-1500")
    assert exc.value.kind == "invalid"
