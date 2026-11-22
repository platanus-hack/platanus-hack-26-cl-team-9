"""Shared sessions over HTTP (docs/sessions-api.md) on the toy world: CRUD, revisions and ETags,
limits, sandbox cuts, nested runs, the SSE stream and the agent OpenAPI conventions."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.api.limits import SessionLocks
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
    "add_substation",
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
    "start_incident_run",
}
TAGS = {"sessions", "session-network", "session-sandbox", "session-runs", "incidents"}


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


SUBSTATION = {
    "name": "SE Nueva",
    "lat": -31.1,
    "lon": -71.0,
    "kv": 220,
    "connections": [{"to": "B002"}, {"to": "B003", "capacity_mw": 200}],
    "load": {"mw": 40, "kind": "consumo"},
}


def test_a_substation_is_created_whole_and_a_bad_one_changes_nothing(client):
    sid = _create(client)
    ok = client.post(f"{BASE}/{sid}/substations", json=SUBSTATION, headers={"If-Match": '"0"'})
    assert ok.status_code == 201 and ok.headers["ETag"] == '"1"'
    body = ok.json()
    assert (body["id"], body["line_ids"], body["load_id"], body["revision"]) == (
        "B006",
        ["U001", "U002"],
        "D001",
        1,
    )
    bad = {**SUBSTATION, "connections": [{"to": "B002"}, {"to": "B999"}]}
    assert client.post(f"{BASE}/{sid}/substations", json=bad).status_code == 404
    seven = {**SUBSTATION, "connections": [{"to": f"B00{i}"} for i in range(7)]}
    assert client.post(f"{BASE}/{sid}/substations", json=seven).status_code == 422
    assert client.get(f"{BASE}/{sid}").json()["revision"] == 1


def test_a_scenario_reset_replaces_the_substation(client):
    sid = _create(client)
    client.post(f"{BASE}/{sid}/substations", json=SUBSTATION)
    out = client.post(f"{BASE}/{sid}/reset", json={"scenario": {"out_buses": ["B004"]}})
    assert out.status_code == 200
    overlay = client.get(f"{BASE}/{sid}").json()["overlay"]
    assert overlay["buses"] == [] and overlay["bus_overrides"]["B004"] == {"in_service": False}
    other = client.post(f"{BASE}/{sid}/reset", json={"scenario": {"point": "feb2025-1500"}})
    assert other.status_code == 422


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


def test_a_chunked_body_over_64_kb_gives_413_and_a_small_one_passes(client):
    sid = _create(client)
    big = json.dumps({**DC, "name": "x" * 70000}).encode()
    r = client.post(f"{BASE}/{sid}/loads", content=(big[i : i + 8192] for i in range(0, len(big), 8192)))
    assert r.status_code == 413 and r.json() == {"detail": "Cuerpo demasiado grande (máximo 64 KB)."}
    small = json.dumps(DC).encode()
    ok = client.post(
        f"{BASE}/{sid}/loads",
        content=(small[i : i + 16] for i in range(0, len(small), 16)),
        headers={"content-type": "application/json"},
    )
    assert ok.status_code == 201


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


def test_run_activity_does_not_invalidate_if_match(client):
    sid = _create(client)
    added = client.post(f"{BASE}/{sid}/loads", json=DC)
    assert added.headers["ETag"] == '"1"' and added.json()["dataset_revision"] == 1
    rid = client.post(f"{BASE}/{sid}/runs", json={"template": "open_field", "seed": 3, "horizon": 8}).json()[
        "run_id"
    ]
    stepped = client.post(f"{BASE}/{sid}/runs/{rid}/step", json={"cycles": 1})
    assert stepped.headers["ETag"] == '"3"'
    net = client.get(f"{BASE}/{sid}/network")
    assert net.headers["ETag"] == '"1"' and net.json()["revision"] == 3
    again = client.post(f"{BASE}/{sid}/loads", json=DC, headers={"If-Match": '"1"'})
    assert again.status_code == 201 and again.headers["ETag"] == '"2"'


def test_the_event_stream_reports_a_change_made_while_open(app, client):
    sid = _create(client)
    slots = app.state.sse_slots

    def edit_once_the_stream_is_open():
        for _ in range(200):
            if slots._open:
                break
            time.sleep(0.005)
        assert TestClient(app).post(f"{BASE}/{sid}/loads", json=DC).status_code == 201

    editor = threading.Thread(target=edit_once_the_stream_is_open)
    with client.stream("GET", f"{BASE}/{sid}/events") as r:
        editor.start()
        lines = list(r.iter_lines())
    editor.join()
    data = [json.loads(line[len("data: ") :]) for line in lines if line.startswith("data: ")]
    assert [d["revision"] for d in data] == [0, 1]
    assert data[1]["op"] == "load_added" and data[1]["dataset_revision"] == 1
    assert lines.count("event: revision") == 2 and "id: 1" in lines


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


def test_rate_limits_key_on_the_address_the_trusted_proxy_appended(app):
    app.state.settings = app.state.settings.model_copy(update={"trusted_proxy_hops": 2})
    client = TestClient(app)
    for i in range(3):  # a spoofed left-most entry changes on every call; the viewer address does not
        headers = {"X-Forwarded-For": f"10.0.0.{i}, 203.0.113.7, 130.176.0.1"}
        assert client.post(BASE, json={}, headers=headers).status_code == 201
    spoofed = client.post(BASE, json={}, headers={"X-Forwarded-For": "10.9.9.9, 203.0.113.7, 130.176.0.1"})
    assert spoofed.status_code == 429
    other = client.post(BASE, json={}, headers={"X-Forwarded-For": "203.0.113.8, 130.176.0.1"})
    assert other.status_code == 201


def test_global_runs_are_rate_limited_and_body_capped(app):
    app.state.settings = app.state.settings.model_copy(update={"rate_writes_per_minute": 2})
    client = TestClient(app)
    for _ in range(2):
        assert client.post("/api/v1/sim/runs", json={"seed": 1, "horizon": 4}).status_code == 201
    limited = client.post("/api/v1/sim/runs", json={"seed": 1, "horizon": 4})
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    big = client.post(
        "/api/v1/sim/runs", content=b"{" + b" " * 70000 + b"}", headers={"Content-Type": "application/json"}
    )
    assert big.status_code == 413


def _slow_state(app, monkeypatch) -> list[tuple[float, float]]:
    """Make the sandbox state read take 0.3 s and record its (start, end)."""
    spans, real = [], app.state.sessions.state

    def slow(sid):
        start = time.monotonic()
        time.sleep(0.3)
        out = real(sid)
        spans.append((start, time.monotonic()))
        return out

    monkeypatch.setattr(app.state.sessions, "state", slow)
    return spans


def _overlap(spans: list[tuple[float, float]]) -> bool:
    first, second = sorted(spans)
    return second[0] < first[1]


def test_requests_on_one_session_run_one_after_another(app, client, monkeypatch):
    sid = _create(client)
    spans = _slow_state(app, monkeypatch)
    with ThreadPoolExecutor(2) as pool:
        codes = list(pool.map(lambda _: client.get(f"{BASE}/{sid}/state").status_code, range(2)))
    assert codes == [200, 200] and len(spans) == 2 and not _overlap(spans)


def test_requests_on_two_sessions_run_in_parallel(app, client, monkeypatch):
    sids = [_create(client), _create(client)]
    spans = _slow_state(app, monkeypatch)
    with ThreadPoolExecutor(2) as pool:
        codes = list(pool.map(lambda sid: client.get(f"{BASE}/{sid}/state").status_code, sids))
    assert codes == [200, 200] and len(spans) == 2 and _overlap(spans)


def test_a_request_that_cannot_get_the_lock_gets_409(app, client):
    sid = _create(client)
    app.state.session_locks = SessionLocks(0.2)
    with app.state.session_locks.hold(sid):
        busy = client.post(f"{BASE}/{sid}/cut", json={"lines": ["R1"]})
    assert busy.status_code == 409 and "ocupada" in busy.json()["detail"]
    assert busy.headers["Retry-After"] == "1"
    assert client.post(f"{BASE}/{sid}/cut", json={"lines": ["R1"]}).status_code == 200
    assert len(app.state.session_locks) == 0


def _documented(app, operation_id: str):
    """The model a route documents for its success body (agent_openapi.ok)."""
    route = next(
        r for r in iter_route_contexts(app.routes) if getattr(r, "operation_id", None) == operation_id
    )
    return route.responses[route.status_code or 200]["model"]


def test_responses_match_the_documented_models(app, client):
    calls = [("create_session", "post", BASE, {})]
    r = client.post(BASE, json={})
    sid = r.json()["session_id"]
    s = f"{BASE}/{sid}"
    calls += [
        ("get_session", "get", s, None),
        ("get_session_network", "get", f"{s}/network", None),
        ("add_bus", "post", f"{s}/buses", {"name": "SE Nueva", "lat": -31.1, "lon": -71.0, "kv": 220}),
        ("update_bus", "patch", f"{s}/buses/B006", {"name": "SE Otra"}),
        ("add_line", "post", f"{s}/lines", {"a": "B006", "b": "B002", "kv": 220, "capacity_mw": 300}),
        ("update_line", "patch", f"{s}/lines/U001", {"capacity_mw": 400}),
        ("add_load", "post", f"{s}/loads", DC),
        ("update_load", "patch", f"{s}/loads/D001", {"mw": 90}),
        ("add_generator", "post", f"{s}/generators", {"bus": "B006", "mw": 50, "tech": "solar"}),
        ("update_generator", "patch", f"{s}/generators/G001", {"mw": 40}),
        ("delete_generator", "delete", f"{s}/generators/G001", None),
        ("delete_load", "delete", f"{s}/loads/D001", None),
        ("delete_line", "delete", f"{s}/lines/U001", None),
        ("delete_bus", "delete", f"{s}/buses/B006", None),
        ("reset_session", "post", f"{s}/reset", None),
        ("cut_lines", "post", f"{s}/cut", {"lines": ["R1"]}),
        ("get_cut_state", "get", f"{s}/state", None),
        ("repair_lines", "post", f"{s}/repair", {"all": True}),
    ]
    for op, method, url, body in calls[1:]:
        r = client.request(method, url, json=body)
        assert r.status_code < 300, (op, r.text)
        _documented(app, op).model_validate(r.json())
    _documented(app, "create_session").model_validate(client.post(BASE, json={}).json())
    run = client.post(f"{s}/runs", json={"seed": 3, "horizon": 8})
    _documented(app, "create_run").model_validate(run.json())
    rid = run.json()["run_id"]
    t = f"{s}/runs/{rid}"
    for op, method, url, body in [
        ("get_run", "get", t, None),
        ("inject_run_event", "post", f"{t}/events", {"type": "C3_transmission_opening", "target": "T2-T3"}),
        ("step_run", "post", f"{t}/step", {"cycles": 1}),
        (
            "submit_run_action",
            "post",
            f"{t}/actions",
            {"action": "restore_element", "target": "T2-T3", "role": "operations"},
        ),
        ("get_run", "get", t, None),
        ("replay_run", "post", f"{t}/replay", {"policy": "A"}),
        ("get_run_snapshots", "get", f"{t}/snapshots", None),
        ("get_run_trace", "get", f"{t}/trace", None),
        ("get_run_report", "get", f"{t}/report", None),
        ("get_run_after_action", "get", f"{t}/after_action", None),
    ]:
        r = client.request(method, url, json=body)
        assert r.status_code < 300, (op, r.text)
        _documented(app, op).model_validate(r.json())
