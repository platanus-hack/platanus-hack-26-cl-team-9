"""Strategic runs over HTTP (docs/stack.md 7.1) on the toy grid."""

import pytest
from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.application.grid_queries import GridQueryService
from cascadasen.application.run_experiment import RunCache
from cascadasen.application.simulation_service import SimulationService


def test_catalog_lists_choices(sim_client):
    cat = sim_client.get("/api/v1/sim/catalog").json()
    assert {"events", "actions", "policies", "objectives", "templates"} <= set(cat)
    assert {p["id"] for p in cat["policies"]} == {"A", "B", "C"}
    assert any(t["id"] == "flagship_observability" for t in cat["templates"])


def test_select_a_node_trigger_step_and_read(sim_client):
    run = sim_client.post("/api/v1/sim/runs", json={"policy": "C", "seed": 11, "horizon": 8})
    assert run.status_code == 201
    rid = run.json()["run_id"]
    inj = sim_client.post(
        f"/api/v1/sim/runs/{rid}/events", json={"type": "C3_transmission_opening", "target": "SE_C1"}
    )
    # a real node id behind a mapa 3 bus resolves to the bus and its area
    assert inj.status_code == 200 and inj.json()["area"] == "T2" and inj.json()["resolved_target"] == "B002"
    step = sim_client.post(f"/api/v1/sim/runs/{rid}/step", json={"cycles": 3}).json()
    assert len(step["snapshots"]) == 3 and step["snapshots"][0]["events"][0]["source"] == "user"
    snap = step["snapshots"][-1]
    assert {"real", "observed", "estimated", "decisions", "metrics"} <= set(snap)
    state = sim_client.get(f"/api/v1/sim/runs/{rid}").json()
    assert state["run"]["cycle"] == 3 and len(state["series"]) == 3
    sim_client.post(f"/api/v1/sim/runs/{rid}/step", json={"cycles": 10})
    report = sim_client.get(f"/api/v1/sim/runs/{rid}/report").json()
    assert report["indicators"]["experimental"] is True and report["run"]["finished"]
    assert (
        sim_client.post(
            f"/api/v1/sim/runs/{rid}/events", json={"type": "D1_telemetry_loss", "target": "T1"}
        ).status_code
        == 409
    )


def test_replay_reproduces_and_changes_policy(sim_client):
    rid = sim_client.post("/api/v1/sim/runs", json={"policy": "A", "seed": 5, "horizon": 6}).json()["run_id"]
    sim_client.post(f"/api/v1/sim/runs/{rid}/events", json={"type": "D4_comms_loss", "target": "T3"})
    sim_client.post(f"/api/v1/sim/runs/{rid}/step", json={"cycles": 6})
    head = sim_client.get(f"/api/v1/sim/runs/{rid}/trace").json()
    assert head["verified"] and head["recipe"]["injected"][0]["target"] == "T3"
    same = sim_client.post(f"/api/v1/sim/runs/{rid}/replay", json={}).json()
    assert sim_client.get(f"/api/v1/sim/runs/{same['run_id']}/trace").json()["head"] == head["head"]
    other = sim_client.post(f"/api/v1/sim/runs/{rid}/replay", json={"policy": "B"}).json()
    assert other["policy"] == "B" and other["replay_of"] == rid


def test_replay_applies_adversary_and_capability_overrides(sim_client):
    rid = sim_client.post("/api/v1/sim/runs", json={"policy": "A", "seed": 5, "horizon": 6}).json()["run_id"]
    sim_client.post(f"/api/v1/sim/runs/{rid}/step", json={"cycles": 3})
    pool = next(iter(sim_client.get("/api/v1/sim/catalog").json()["resources"]))
    adversary = {"enabled": True, "objective": "raise_uncertainty", "budget": 5, "adaptive": False}
    out = sim_client.post(
        f"/api/v1/sim/runs/{rid}/replay",
        json={"adversary": adversary, "capabilities": {pool: 7}, "seed": 9, "uncertainty": 1.5},
    ).json()
    assert out["overrides"] == {
        "seed": 9,
        "uncertainty": 1.5,
        "adversary": {**adversary, "budget": 5.0, "mode": "exp3", "propagation": None},
        "capabilities": [[pool, 7.0]],
    }
    assert out["replay_of"] == rid and out["seed"] == 9 and out["uncertainty"] == 1.5
    assert out["adversary"]["objective"] == "raise_uncertainty" and out["adversary"]["adaptive"] is False
    assert out["policy"] == "A" and out["cycle"] == 3


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
def test_run_creation_errors(sim_client, body, code):
    assert sim_client.post("/api/v1/sim/runs", json=body).status_code == code


def test_unknown_run_and_event_errors(sim_client):
    assert sim_client.get("/api/v1/sim/runs/nope").status_code == 404
    rid = sim_client.post("/api/v1/sim/runs", json={}).json()["run_id"]
    assert (
        sim_client.post(f"/api/v1/sim/runs/{rid}/events", json={"type": "XX", "target": "T1"}).status_code
        == 422
    )
    assert (
        sim_client.post(
            f"/api/v1/sim/runs/{rid}/events", json={"type": "D1_telemetry_loss", "target": "NOPE"}
        ).status_code
        == 404
    )


def test_narrative_and_after_action(sim_client):
    nar = sim_client.get("/api/v1/sim/narrative").json()
    assert nar["notice"].startswith("Escenario hipotético") and "rationale" in nar
    rid = sim_client.post(
        "/api/v1/sim/runs",
        json={
            "horizon": 4,
            "auto_run": True,
            "initial_events": [{"type": "D4_comms_loss", "target": "T2", "cycle": 1}],
        },
    ).json()["run_id"]
    aar = sim_client.get(f"/api/v1/sim/runs/{rid}/after_action").json()
    assert aar["summary"][0].startswith("La organización mantuvo el")
    assert any("Pérdida de comunicaciones en T2" in line for c in aar["timeline"] for line in c["lines"])


def test_replay_snapshots_can_be_read_back(sim_client):
    rid = sim_client.post("/api/v1/sim/runs", json={"policy": "A", "seed": 5, "horizon": 4}).json()["run_id"]
    sim_client.post(f"/api/v1/sim/runs/{rid}/step", json={"cycles": 4})
    other = sim_client.post(f"/api/v1/sim/runs/{rid}/replay", json={"policy": "C"}).json()
    snaps = sim_client.get(f"/api/v1/sim/runs/{other['run_id']}/snapshots").json()["snapshots"]
    assert [s["cycle"] for s in snaps] == [0, 1, 2, 3]
    tail = sim_client.get(f"/api/v1/sim/runs/{other['run_id']}/snapshots", params={"start": 2}).json()[
        "snapshots"
    ]
    assert [s["cycle"] for s in tail] == [2, 3]


def test_an_evicted_run_is_served_rebuilt(toy_snapshot, toy_network, toy_world):
    sim = SimulationService(toy_network, world=toy_world, run_cache=RunCache(1))
    client = TestClient(create_app(service=GridQueryService(toy_snapshot), simulation=sim))
    a = client.post("/api/v1/sim/runs", json={"seed": 3, "horizon": 6}).json()["run_id"]
    client.post(f"/api/v1/sim/runs/{a}/step", json={"cycles": 2})
    head = client.get(f"/api/v1/sim/runs/{a}/trace").json()["head"]
    assert client.post("/api/v1/sim/runs", json={"seed": 4}).status_code == 201  # evicts A
    state = client.get(f"/api/v1/sim/runs/{a}")
    assert state.status_code == 200
    run = state.json()["run"]
    assert run["rebuilt"] is True and run["trace_matches"] is True and run["cycle"] == 2
    assert client.get(f"/api/v1/sim/runs/{a}/trace").json()["head"] == head


def _documented(app, operation_id: str):
    """The model a route documents for its success body (agent_openapi.ok)."""
    route = next(
        r for r in iter_route_contexts(app.routes) if getattr(r, "operation_id", None) == operation_id
    )
    return route.responses[route.status_code or 200]["model"]


def test_responses_match_the_documented_models(sim_client):
    rid = sim_client.post("/api/v1/sim/runs", json={"seed": 11, "horizon": 6}).json()["run_id"]
    r = f"/api/v1/sim/runs/{rid}"
    for op, method, url, body in [
        ("global_get_network", "get", "/api/v1/sim/network", None),
        ("get_catalog", "get", "/api/v1/sim/catalog", None),
        ("global_get_run", "get", r, None),
        ("global_inject_run_event", "post", f"{r}/events", {"type": "D1_telemetry_loss", "target": "T1"}),
        ("global_step_run", "post", f"{r}/step", {"cycles": 2}),
        ("global_get_run", "get", r, None),
        ("global_get_run_snapshots", "get", f"{r}/snapshots", None),
        ("global_get_run_trace", "get", f"{r}/trace", None),
        ("global_get_run_report", "get", f"{r}/report", None),
        ("global_get_run_after_action", "get", f"{r}/after_action", None),
    ]:
        resp = sim_client.request(method, url, json=body)
        assert resp.status_code == 200, (op, resp.text)
        _documented(sim_client.app, op).model_validate(resp.json())
