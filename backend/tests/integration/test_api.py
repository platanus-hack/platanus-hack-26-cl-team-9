import pytest
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.application.grid_queries import GridQueryService
from cascadasen.domain.validation import validate_snapshot
from cascadasen.infrastructure.settings import Settings


@pytest.fixture
def client(toy_snapshot):
    toy_snapshot.stats["validation"] = validate_snapshot(toy_snapshot)
    return TestClient(create_app(service=GridQueryService(toy_snapshot)))


def test_health_and_stats(client):
    assert client.get("/api/v1/health").json()["status"] == "ok"
    stats = client.get("/api/v1/stats").json()
    assert stats["nodes_by_kind"]["substation"] == 4
    assert "validation_summary" in stats


def test_nodes_filters_and_detail(client):
    r = client.get("/api/v1/nodes", params={"kv_min": 500}).json()
    assert r["total"] == 2
    d = client.get("/api/v1/nodes/SE102").json()
    assert d["name"] == "S/E BETA"
    assert {c["neighbor"] for c in d["connections"]} >= {"SE101", "SE103", "SE104"}
    assert client.get("/api/v1/nodes/NOPE").status_code == 404


def test_edges_and_electrical_filter(client):
    r = client.get("/api/v1/edges", params={"with_electrical": True}).json()
    assert r["total"] == 1 and r["items"][0]["s_nom_mva"] == 2000.0


def test_islands_endpoint(client, toy_snapshot):
    cut = next(e.id for e in toy_snapshot.edges if e.ids.get("ide_objectid") == "12")
    r = client.post("/api/v1/graph/islands", json={"remove": [cut]})
    assert r.status_code == 200 and r.json()["new_islands"] == 1
    assert client.post("/api/v1/graph/islands", json={"remove": []}).status_code == 422
    assert client.post("/api/v1/graph/islands", json={"remove": ["X"]}).status_code == 404


def test_geojson_layers(client):
    for layer in ("substations", "lines", "plants", "comunas", "taps", "storage"):
        fc = client.get(f"/api/v1/geo/{layer}.geojson").json()
        assert fc["type"] == "FeatureCollection"
    assert client.get("/api/v1/geo/nope.geojson").status_code == 404


def test_zones_validation_sources_and_map(client):
    assert client.get("/api/v1/zones").json()["zones"]
    assert client.get("/api/v1/validation").json()["checks"]
    assert client.get("/api/v1/sources").json()[0]["id"] == "ide_energia"
    page = client.get("/map")
    assert page.status_code == 200 and "Atlas de la" in page.text


def test_service_unavailable_without_snapshot(toy_snapshot):
    app = create_app(service=GridQueryService(toy_snapshot))
    app.state.service = None
    c = TestClient(app)
    assert c.get("/api/v1/nodes").status_code == 503
    assert c.get("/api/v1/health").json()["status"] == "sin snapshot"


def test_admin_reload_is_off_unless_enabled(toy_snapshot, tmp_path):
    off = TestClient(create_app(service=GridQueryService(toy_snapshot), settings=Settings(data_dir=tmp_path)))
    assert off.post("/api/v1/admin/reload").status_code == 404
    on = TestClient(
        create_app(
            service=GridQueryService(toy_snapshot), settings=Settings(data_dir=tmp_path, admin_enabled=True)
        )
    )
    res = on.post("/api/v1/admin/reload")
    assert res.status_code == 200 and res.json()["status"] == "sin snapshot"  # nothing in tmp_path
