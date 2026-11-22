"""POST /api/v1/simulate and GET /api/v1/sim/network on the toy grid (docs/stack.md 7)."""

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


def test_network_lists_selectable_targets(client):
    net = client.get("/api/v1/simulate/network").json()
    assert [a["id"] for a in net["areas"]] == ["T1", "T2", "T3"]
    t2 = next(a for a in net["areas"] if a["id"] == "T2")
    assert "SE104" in t2["aggregates"] and t2["main_node"] == "SE102"
    assert {c["id"] for c in net["corridors"]} == {"T1-T2/500", "T2-T3/220"}


def test_simulate_returns_timeline_contract(client):
    r = client.post(
        "/api/v1/simulate",
        json={"scenario": "midday_2026", "defenses": "design_2026", "elements_out": ["T2-T3/220"]},
    )
    assert r.status_code == 200
    tl = r.json()
    for key in (
        "scenario",
        "defenses",
        "behavior",
        "failed_elements",
        "duration_s",
        "truncated",
        "events",
        "frames",
        "summary",
        "provenance",
    ):
        assert key in tl
    assert tl["events"][0]["type"] == "line_cut"
    assert tl["summary"]["consequence_level"] in ("L0", "L1", "L2", "L3")
    assert {"t", "edges", "nodes", "islands"} <= set(tl["frames"][0])
    assert all("is_assumption" in p for p in tl["provenance"])


def test_simulate_accepts_a_real_substation_id_and_labels_cyber_effect(client):
    r = client.post(
        "/api/v1/simulate",
        json={
            "scenario": "midday_2026",
            "defenses": "design_2026",
            "elements_out": ["SE104"],
            "cause": "cyber_effect",
            "frames": False,
        },
    )
    tl = r.json()
    assert r.status_code == 200 and tl["elements_resolved"][0]["area"] == "T2"
    assert tl["notice"] == "Escenario hipotético: se modela el efecto, no el ataque."
    assert tl["frames"] == []


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"scenario": "x", "defenses": "25F", "elements_out": ["T2"]}, "scenario"),
        ({"scenario": "midday_2026", "defenses": "x", "elements_out": ["T2"]}, "defenses"),
        (
            {"scenario": "midday_2026", "defenses": "25F", "behavior": "as_happened", "elements_out": ["T2"]},
            "behavior",
        ),
        ({"scenario": "midday_2026", "defenses": "25F", "elements_out": []}, "elements_out"),
        ({"scenario": "midday_2026", "defenses": "25F", "elements_out": ["NOPE"]}, "elements_out"),
        (
            {
                "scenario": "midday_2026",
                "defenses": "25F",
                "elements_out": ["T2"],
                "battery_mw": {"T2": 9000},
            },
            "battery_mw",
        ),
        (
            {
                "scenario": "midday_2026",
                "defenses": "25F",
                "elements_out": ["T2"],
                "defenses_disabled": ["x"],
            },
            "defenses_disabled",
        ),
        (
            {"scenario": "midday_2026", "defenses": "25F", "elements_out": ["T2"], "outage_duration_h": 9999},
            "outage_duration_h",
        ),
    ],
)
def test_simulate_rejects_invalid_input(client, body, field):
    r = client.post("/api/v1/simulate", json=body)
    assert r.status_code == 422 and r.json()["detail"]["field"] == field


def test_simulation_unavailable_without_snapshot(toy_snapshot):
    app = create_app(service=GridQueryService(toy_snapshot))
    app.state.service = None
    assert TestClient(app).get("/api/v1/sim/network").status_code == 503


def test_theater_network_is_the_mapa3_network(client):
    """GET /sim/network serves the mapa 3 Network (B###, R###) plus the theatre's areas."""
    net = client.get("/api/v1/sim/network").json()
    ids = {n["id"] for n in net["nodes"]}
    assert ids == {f"B{i:03d}" for i in range(6)} and all(ln["id"].startswith("R") for ln in net["lines"])
    assert all(x["country"] == "CHL" for x in net["nodes"] + net["lines"])
    assert [a["id"] for a in net["areas"]] == ["T1", "T2", "T3"]
    assert {c["id"] for c in net["corridors"]} == {"T1-T2", "T2-T3"}
    assert all(set(a["buses"]) <= ids and a["anchor_bus"] in a["buses"] for a in net["areas"])
    assert client.get("/api/v1/sim/network", params={"point": "nope"}).status_code == 404
