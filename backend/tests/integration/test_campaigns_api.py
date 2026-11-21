"""Campaigns over HTTP (modes I, II, III) on the toy grid, and the two campaign indices."""

import pytest
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.application.grid_queries import GridQueryService
from cascadasen.application.simulation_service import SimulationService


@pytest.fixture
def client(toy_snapshot, toy_network, toy_world):
    return TestClient(
        create_app(
            service=GridQueryService(toy_snapshot), simulation=SimulationService(toy_network, world=toy_world)
        )
    )


def _campaign(client, **body):
    base = {"templates": ["open_field"], "seeds": [1, 2], "horizon": 8}
    base.update(body)
    return client.post("/api/v1/sim/campaigns", json=base)


def test_adversarial_campaign_adds_perfect_information_pairs(client):
    r = _campaign(
        client,
        mode="adversarial",
        policies=["A", "C"],
        uncertainty_levels=[1.0],
        objective="raise_uncertainty",
        budget=6,
    )
    assert r.status_code == 201
    res = r.json()
    assert res["runs"] == 2 * 2 * 2 * 2  # policies x levels (0 added) x adversaries x seeds
    assert {row["uncertainty"] for row in res["table"]} == {0.0, 1.0}
    assert res["indices"]["decisional_fragility"] and res["indices"]["adaptation"]
    assert res["experimental"] is True and res["notice"].startswith("Escenario hipotético")
    assert client.get(f"/api/v1/sim/campaigns/{res['campaign_id']}").status_code == 200


def test_indices_are_neutral_when_nothing_differs(client):
    res = _campaign(client, mode="adversarial", policies=["A"], uncertainty_levels=[1.0], budget=0).json()
    assert all(x["value"] == pytest.approx(1.0) for x in res["indices"]["adaptation"])
    assert all(x["value"] == pytest.approx(0.0, abs=1e-3) for x in res["indices"]["decisional_fragility"])


def test_capability_campaign_reports_deltas_against_baseline(client):
    res = _campaign(
        client,
        mode="capability",
        policies=["C"],
        objective="pressure_resources",
        budget=8,
        capability_variants=[
            {"id": "baseline", "capabilities": {}},
            {"id": "more_crews", "capabilities": {"field_crews": 12}},
        ],
    ).json()
    assert [d["capability"] for d in res["capability_deltas"]] == ["more_crews"]


def test_diagnostic_campaign_lists_areas_in_geographic_order(client):
    res = _campaign(client, mode="diagnostic", policies=["C"], seeds=[1]).json()
    assert [a["area"] for a in res["areas"]] == ["T1", "T2", "T3"]


def test_campaign_errors(client):
    assert _campaign(client, templates=["nope"]).status_code == 404
    assert _campaign(client, mode="nope").status_code == 422
    assert (
        _campaign(
            client,
            seeds=list(range(10)),
            uncertainty_levels=[1, 2],
            policies=["A", "B", "C"],
            templates=["open_field", "open_field"],
        ).status_code
        == 422
    )
    assert client.get("/api/v1/sim/campaigns/nope").status_code == 404


def test_random_seeds_are_drawn_returned_and_paired(client):
    r = _campaign(
        client, mode="adversarial", policies=["A", "C"], random_seeds=3, adversary_variants=["adaptive"]
    )
    assert r.status_code == 201
    res = r.json()
    seeds = res["spec"]["seeds"]
    assert len(seeds) == 3 and len(set(seeds)) == 3 and seeds != [1, 2, 3]
    for row in res["table"]:
        assert row["runs"] == 3  # the same seeds in every cell
        s = row["spread"]["mission_continuity"]
        assert s["p10"] <= s["p50"] <= s["p90"]
    assert _campaign(client, random_seeds=11).status_code == 422


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def test_no_response_exposes_adversary_weights(client):
    """cyber.md 8 item 7: the adversary's learned preferences over areas never leave the engine."""
    body = {
        "template": "open_field",
        "horizon": 8,
        "adversary": {"enabled": True, "objective": "complicate_recovery", "budget": 10, "adaptive": True},
    }
    run = client.post("/api/v1/sim/runs", json=body).json()
    rid = run["run_id"]
    payloads = [
        run,
        client.post(f"/api/v1/sim/runs/{rid}/step", json={"cycles": 8}).json(),
        client.get(f"/api/v1/sim/runs/{rid}").json(),
        client.get(f"/api/v1/sim/runs/{rid}/trace").json(),
        client.get(f"/api/v1/sim/runs/{rid}/report").json(),
        _campaign(client, mode="adversarial", policies=["C"], adversary_variants=["adaptive"]).json(),
    ]
    forbidden = {"weights", "arms", "probs", "ranking"}
    for p in payloads:
        assert forbidden.isdisjoint(_keys(p))
