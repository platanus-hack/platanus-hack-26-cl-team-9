"""Shared sessions over HTTP (docs/sessions-api.md) on the toy world: CRUD, revisions and ETags,
limits, sandbox cuts, nested runs, the SSE stream and the agent OpenAPI conventions."""

import pytest
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.application.grid_queries import GridQueryService
from cascadasen.application.run_experiment import RunCache
from cascadasen.application.sessions import SessionService
from cascadasen.application.simulation_service import SimulationService
from cascadasen.domain.simulation.grid import Physics
from cascadasen.infrastructure.document_store import MemoryDocumentStore
from cascadasen.infrastructure.settings import Settings

BASE = "/api/v1/sessions"
DC = {"bus": "B002", "mw": 100, "kind": "datacenter", "name": "DC Toy"}
OPERATION_IDS = {
    "create_session",
    "get_session",
    "delete_session",
    "get_session_network",
    "add_bus",
    "update_bus",
    "delete_bus",
    "add_line",
    "update_line",
    "delete_line",
    "add_load",
    "update_load",
    "delete_load",
    "add_generator",
    "update_generator",
    "delete_generator",
    "reset_session",
    "cut_lines",
    "repair_lines",
    "get_cut_state",
    "create_run",
    "get_run",
    "inject_run_event",
    "step_run",
    "replay_run",
    "get_run_snapshots",
    "get_run_trace",
    "get_run_report",
    "get_run_after_action",
    "submit_run_action",
}
TAGS = {"sessions", "session-network", "session-sandbox", "session-runs"}


@pytest.fixture(scope="module")
def physics():
    return Physics.load()


@pytest.fixture
def app(toy_snapshot, toy_network, toy_world, toy_spec, physics):
    store, cache = MemoryDocumentStore(), RunCache()
    return create_app(
        service=GridQueryService(toy_snapshot),
        simulation=SimulationService(toy_network, physics, world=toy_world, store=store, run_cache=cache),
        sessions=SessionService(toy_world, physics, store, cache, spec=toy_spec),
        settings=Settings(sse_max_s=0.5, sse_poll_s=0.05, sse_head_s=0.1, rate_create_per_hour=3),
    )


@pytest.fixture
def client(app):
    return TestClient(app)


def _create(client) -> str:
    r = client.post(BASE, json={})
    assert r.status_code == 201, r.text
    return r.json()["session_id"]


def test_create_edit_and_read_the_network(client):
    r = client.post(BASE, json={"label": "Equipo"}, headers={"X-Sub50-Agent": "bot-1"})
    doc = r.json()
    sid = doc["session_id"]
    assert doc["revision"] == 0 and doc["point"] == "nov2026-1300" and r.headers["ETag"] == '"0"'
    assert doc["share_path"] == f"/?sesion={sid}" and doc["last_op"]["by"] == "bot-1"
    added = client.post(f"{BASE}/{sid}/loads", json=DC)
    assert added.status_code == 201 and added.json()["id"] == "D001" and added.headers["ETag"] == '"1"'
    net = client.get(f"{BASE}/{sid}/network").json()
    assert net["buses"]["B002"]["load_mw"] == 250.0
    assert net["loads"][0]["origin"] == "session" and net["balance"][0]["is_assumption"] is True
    assert all(n["origin"] == "base" for n in net["nodes"])


def test_a_second_client_sees_the_etag_move(app, client):
    sid = _create(client)
    other = TestClient(app)
    first = other.get(f"{BASE}/{sid}")
    assert first.headers["ETag"] == '"0"'
    assert other.get(f"{BASE}/{sid}", headers={"If-None-Match": '"0"'}).status_code == 304
    client.post(f"{BASE}/{sid}/loads", json=DC)
    moved = other.get(f"{BASE}/{sid}", headers={"If-None-Match": '"0"'})
    assert moved.status_code == 200 and moved.headers["ETag"] == '"1"'


def test_a_stale_if_match_gives_412(client):
    sid = _create(client)
    assert client.post(f"{BASE}/{sid}/loads", json=DC, headers={"If-Match": '"0"'}).status_code == 201
    stale = client.post(f"{BASE}/{sid}/loads", json=DC, headers={"If-Match": '"0"'})
    assert stale.status_code == 412


def test_deleting_a_bus_with_dependents_gives_409(client):
    sid = _create(client)
    bus = client.post(f"{BASE}/{sid}/buses", json={"name": "SE Nueva", "lat": -31.1, "lon": -71.0, "kv": 220})
    assert bus.status_code == 201 and bus.json()["id"] == "B006"
    line = client.post(f"{BASE}/{sid}/lines", json={"a": "B006", "b": "B002", "kv": 220, "capacity_mw": 300})
    assert line.status_code == 201 and line.json()["id"] == "U001"
    assert client.post(f"{BASE}/{sid}/loads", json={**DC, "bus": "B006"}).status_code == 201
    conflict = client.delete(f"{BASE}/{sid}/buses/B006")
    assert conflict.status_code == 409 and "U001" in conflict.json()["detail"]["valid"]
    assert client.delete(f"{BASE}/{sid}/lines/R0").status_code == 409  # base lines are never deleted
    patched = client.patch(f"{BASE}/{sid}/lines/U001", json={"capacity_mw": 400})
    assert patched.status_code == 200 and patched.json()["revision"] == 4
    gen = client.post(f"{BASE}/{sid}/generators", json={"bus": "B006", "mw": 50, "tech": "solar"})
    assert gen.status_code == 201 and gen.json()["id"] == "G001"
    reset = client.post(f"{BASE}/{sid}/reset")
    assert reset.status_code == 200 and client.get(f"{BASE}/{sid}").json()["overlay"]["loads"] == []


def test_cut_then_repair_all(client):
    sid = _create(client)
    cut = client.post(f"{BASE}/{sid}/cut", json={"lines": ["R1"]})
    assert cut.status_code == 200 and cut.json()["open_lines"] == ["R1"]
    assert client.get(f"{BASE}/{sid}/state").json()["open_lines"] == ["R1"]
    assert client.post(f"{BASE}/{sid}/cut", json={"lines": ["R99"]}).status_code == 404
    repaired = client.post(f"{BASE}/{sid}/repair", json={"all": True})
    assert repaired.status_code == 200 and repaired.json()["open_lines"] == []
    assert client.post(f"{BASE}/{sid}/repair", json={}).status_code == 422


def test_session_runs_take_events_steps_and_actions(client):
    sid = _create(client)
    run = client.post(f"{BASE}/{sid}/runs", json={"template": "open_field", "seed": 3, "horizon": 8})
    assert run.status_code == 201, run.text
    rid = run.json()["run_id"]
    assert run.json()["session_revision"] == 1 and run.headers["ETag"] == '"1"'
    assert rid in client.get(f"{BASE}/{sid}").json()["runs"]
    inj = client.post(
        f"{BASE}/{sid}/runs/{rid}/events", json={"type": "C3_transmission_opening", "target": "T2-T3"}
    )
    assert inj.status_code == 200, inj.text
    assert client.post(f"{BASE}/{sid}/runs/{rid}/step", json={"cycles": 1}).status_code == 200
    action = client.post(
        f"{BASE}/{sid}/runs/{rid}/actions",
        json={"action": "restore_element", "target": "T2-T3", "role": "operations", "agent": "bot"},
    )
    assert action.status_code == 200 and action.json()["accepted"] is True
    snap = client.post(f"{BASE}/{sid}/runs/{rid}/step", json={"cycles": 1}).json()["snapshots"][0]
    assert any(e["action"] == "restore_element" for e in snap["executed"])
    assert client.get(f"{BASE}/{sid}/runs/{rid}/trace").json()["verified"] is True
    assert client.get(f"{BASE}/{sid}/runs/{rid}").json()["run"]["cycle"] == 2
    assert len(client.get(f"{BASE}/{sid}/runs/{rid}/snapshots", params={"start": 1}).json()["snapshots"]) == 1
    assert client.get(f"{BASE}/{sid}/runs/{rid}/report").status_code == 200
    replay = client.post(f"{BASE}/{sid}/runs/{rid}/replay", json={"policy": "A"})
    assert replay.status_code == 201 and replay.json()["replay_of"] == rid
    bad_role = client.post(
        f"{BASE}/{sid}/runs/{rid}/actions", json={"action": "restore_element", "target": "T2-T3", "role": "x"}
    )
    assert bad_role.status_code == 422
    assert client.post(f"{BASE}/{sid}/runs", json={"point": "feb2025-1500"}).status_code == 422


def test_invalid_bodies_give_422(client):
    sid = _create(client)
    bad_kv = {"name": "SE", "lat": -31.0, "lon": -71.0, "kv": 66}
    assert client.post(f"{BASE}/{sid}/buses", json=bad_kv).status_code == 422
    assert client.post(f"{BASE}/{sid}/loads", json={**DC, "mw": 0}).status_code == 422
    assert client.post(f"{BASE}/{sid}/loads", json={**DC, "extra": 1}).status_code == 422
    assert client.post(f"{BASE}/{sid}/cut", json={"lines": []}).status_code == 422


def test_the_fourth_create_gives_429(client):
    for _ in range(3):
        _create(client)
    r = client.post(BASE, json={})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1


def test_a_body_over_64_kb_gives_413(client):
    sid = _create(client)
    r = client.post(f"{BASE}/{sid}/loads", json={**DC, "name": "x" * 70000})
    assert r.status_code == 413


def test_unknown_and_malformed_sessions_give_404(client):
    assert client.get(f"{BASE}/{'A' * 22}").status_code == 404
    assert client.get(f"{BASE}/no-such").status_code == 404
    assert client.post(f"{BASE}/{'A' * 22}/loads", json=DC).status_code == 404
    sid = _create(client)
    assert client.get(f"{BASE}/{sid}/runs/0123456789ab").status_code == 404
    assert client.delete(f"{BASE}/{sid}").status_code == 204
    assert client.get(f"{BASE}/{sid}").status_code == 404


def test_the_event_stream_starts_with_the_current_revision(client):
    sid = _create(client)
    client.post(f"{BASE}/{sid}/loads", json=DC)
    with client.stream("GET", f"{BASE}/{sid}/events") as r:
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        lines = list(r.iter_lines())
    assert "event: revision" in lines and "id: 1" in lines
    data = next(line for line in lines if line.startswith("data: "))
    assert '"revision": 1' in data and '"op": "load_added"' in data
    assert client.get(f"{BASE}/{'A' * 22}/events").status_code == 404


def test_global_runs_still_work(client):
    assert client.post("/api/v1/sim/runs", json={"seed": 1, "horizon": 4}).status_code == 201


def test_session_routes_follow_the_agent_conventions(app):
    spec = app.openapi()
    ids = [op["operationId"] for path in spec["paths"].values() for op in path.values()]
    assert len(ids) == len(set(ids))
    seen = set()
    for path, ops in spec["paths"].items():
        if not path.startswith(BASE):
            continue
        for method, op in ops.items():
            if path.endswith("/{sid}/events") and method == "get":
                assert "x-sub50-agent" not in op and op["summary"]
                continue
            assert op.get("x-sub50-agent") is True, (method, path)
            assert op["operationId"] in OPERATION_IDS and op["summary"] and op["description"]
            assert set(op["tags"]) <= TAGS
            for code, resp in op["responses"].items():
                if code.startswith("4"):
                    ref = resp["content"]["application/json"]["schema"]["$ref"]
                    assert ref.endswith("/ErrorResponse"), (path, code)
            seen.add(op["operationId"])
    assert seen == OPERATION_IDS
