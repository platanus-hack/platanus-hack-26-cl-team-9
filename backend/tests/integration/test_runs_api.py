"""Strategic runs over HTTP (docs/stack.md 7.1) on the toy grid."""

import pytest
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.application.grid_queries import GridQueryService
from cascadasen.application.simulation_service import SimulationService


@pytest.fixture
def client(toy_snapshot, toy_network):
    return TestClient(
        create_app(service=GridQueryService(toy_snapshot), simulation=SimulationService(toy_network))
    )


def test_catalog_lists_choices(client):
    cat = client.get("/api/v1/sim/catalog").json()
    assert {"events", "actions", "policies", "objectives", "templates"} <= set(cat)
    assert {p["id"] for p in cat["policies"]} == {"A", "B", "C"}
    assert any(t["id"] == "flagship_observability" for t in cat["templates"])


def test_select_a_node_trigger_step_and_read(client):
    run = client.post("/api/v1/sim/runs", json={"policy": "C", "seed": 11, "horizon": 8})
    assert run.status_code == 201
    rid = run.json()["run_id"]
    inj = client.post(
        f"/api/v1/sim/runs/{rid}/events", json={"type": "C3_transmission_opening", "target": "SE104"}
    )
    assert inj.status_code == 200 and inj.json()["area"] == "T2"
    step = client.post(f"/api/v1/sim/runs/{rid}/step", json={"cycles": 3}).json()
    assert len(step["snapshots"]) == 3 and step["snapshots"][0]["events"][0]["source"] == "user"
    snap = step["snapshots"][-1]
    assert {"real", "observed", "estimated", "decisions", "metrics"} <= set(snap)
    state = client.get(f"/api/v1/sim/runs/{rid}").json()
    assert state["run"]["cycle"] == 3 and len(state["series"]) == 3
    client.post(f"/api/v1/sim/runs/{rid}/step", json={"cycles": 10})
    report = client.get(f"/api/v1/sim/runs/{rid}/report").json()
    assert report["indicators"]["experimental"] is True and report["run"]["finished"]
    assert (
        client.post(
            f"/api/v1/sim/runs/{rid}/events", json={"type": "D1_telemetry_loss", "target": "T1"}
        ).status_code
        == 409
    )


def test_replay_reproduces_and_changes_policy(client):
    rid = client.post("/api/v1/sim/runs", json={"policy": "A", "seed": 5, "horizon": 6}).json()["run_id"]
    client.post(f"/api/v1/sim/runs/{rid}/events", json={"type": "D4_comms_loss", "target": "T3"})
    client.post(f"/api/v1/sim/runs/{rid}/step", json={"cycles": 6})
    head = client.get(f"/api/v1/sim/runs/{rid}/trace").json()
    assert head["verified"] and head["recipe"]["injected"][0]["target"] == "T3"
    same = client.post(f"/api/v1/sim/runs/{rid}/replay", json={}).json()
    assert client.get(f"/api/v1/sim/runs/{same['run_id']}/trace").json()["head"] == head["head"]
    other = client.post(f"/api/v1/sim/runs/{rid}/replay", json={"policy": "B"}).json()
    assert other["policy"] == "B" and other["replay_of"] == rid


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"template": "nope"}, 404),
        ({"policy": "Z"}, 422),
        ({"uncertainty": 9}, 422),
        ({"capabilities": {"nope": 1}}, 422),
        ({"initial_events": [{"type": "D1_telemetry_loss", "target": "X"}]}, 404),
    ],
)
def test_run_creation_errors(client, body, code):
    assert client.post("/api/v1/sim/runs", json=body).status_code == code


def test_unknown_run_and_event_errors(client):
    assert client.get("/api/v1/sim/runs/nope").status_code == 404
    rid = client.post("/api/v1/sim/runs", json={}).json()["run_id"]
    assert (
        client.post(f"/api/v1/sim/runs/{rid}/events", json={"type": "XX", "target": "T1"}).status_code == 422
    )
    assert (
        client.post(
            f"/api/v1/sim/runs/{rid}/events", json={"type": "D1_telemetry_loss", "target": "NOPE"}
        ).status_code
        == 404
    )
