"""Several edits at once, without a session (application/grid_simulation.py)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.application.grid_simulation import GridSimulator
from cascadasen.application.grids import GridError
from cascadasen.application.theater_world import default_world
from cascadasen.domain.cascade.engine import failure_cost, run_cascade_workflow
from cascadasen.domain.cascade.health import with_event_health
from cascadasen.infrastructure.settings import REPO_ROOT, Settings

PROCESSED = REPO_ROOT / "data/processed"
pytestmark = pytest.mark.skipif(not (PROCESSED / "grid_snapshot.json").exists(), reason="no processed data")
POINT = "feb2025-1500"


@pytest.fixture(scope="module")
def sim() -> GridSimulator:
    return GridSimulator(default_world(str(PROCESSED)))


def test_two_cuts_are_applied_together(sim):
    net, op = sim.world.load(POINT)
    out = sim.simulate_workflow(POINT, ["R239", "R001"], [])
    assert out["open_lines"] == ["R001", "R239"]
    assert out["timeline"] == with_event_health(run_cascade_workflow(net.buses, op, ["R001", "R239"]))
    assert out["timeline"]["failed_elements"] == ["R001", "R239"]


def test_a_substation_out_is_dark_in_every_frame_and_counted_as_direct_loss(sim):
    net, op = sim.world.load(POINT)
    bus = max(range(net.buses.size), key=lambda i: op.load[i])
    out = sim.simulate_workflow(POINT, [], [f"B{bus:03d}"])
    assert all(f"B{bus:03d}" in f["dark"] for f in out["timeline"]["frames"])
    assert out["direct"]["load_mw"] == round(float(op.load[bus]), 1) > 0
    assert out["direct"]["people"] == round(float(op.people[bus]))
    assert (
        out["timeline"]["summary"]["people_without_power"] == out["direct"]["people"]
    )  # no cascade: only the outage
    assert out["timeline"]["summary"]["load_total_mw"] == pytest.approx(float(op.load.sum()), abs=0.2)
    summary = out["timeline"]["summary"]
    assert summary["dark_load_mw"] >= out["direct"]["load_mw"]  # a substation out of service is dark demand
    assert (
        summary["failure_cost_usd"]
        == failure_cost(summary["load_shed_mw"], summary["dark_load_mw"], summary["load_total_mw"])[
            "failure_cost_usd"
        ]
    )
    assert out["timeline"]["health"]["cost"]["cost_usd"] == summary["failure_cost_usd"]


def test_a_line_that_goes_with_its_substation_is_not_cut_twice(sim):
    net, _ = sim.world.load(POINT)
    line = next(ln for ln in net.buses.lines if ln.id == "R239")
    out = sim.simulate_workflow(POINT, ["R239"], [f"B{line.a:03d}"])
    assert out["dropped_lines"] == ["R239"] and out["open_lines"] == []


@pytest.mark.parametrize(
    "args, kind",
    [
        (("nope", ["R239"], []), "not_found"),
        ((POINT, ["R999"], []), "not_found"),
        ((POINT, [], ["B999"]), "not_found"),
        ((POINT, [], []), "invalid"),
        ((POINT, [f"R{i:03d}" for i in range(60)], []), "invalid"),
    ],
)
def test_bad_requests(sim, args, kind):
    with pytest.raises(GridError) as exc:
        sim.simulate_workflow(*args)
    assert exc.value.kind == kind


def test_api_simulate():
    client = TestClient(create_app(settings=Settings(data_dir=REPO_ROOT / "data")))
    ok = client.post("/api/v1/grids/simulate", json={"point": POINT, "open_lines": ["R239", "R001"]})
    assert ok.status_code == 200 and ok.json()["timeline"]["frames"]
    assert client.post("/api/v1/grids/simulate", json={"point": POINT}).status_code == 422
    assert (
        client.post("/api/v1/grids/simulate", json={"point": "x", "open_lines": ["R239"]}).status_code == 404
    )


def _without_boundary_status(timeline: dict, cached: dict) -> dict:
    """Copy `timeline` with `status` taken from `cached` on edges whose loading is exactly 1.0."""
    out = json.loads(json.dumps(timeline, default=float))
    for frame, ref in zip(out["frames"], cached["frames"], strict=True):
        for key, edge in frame["edges"].items():
            other = ref["edges"][key]
            if edge["loading"] == other["loading"] == 1.0 and {edge["status"], other["status"]} <= {
                "ok",
                "overload",
            }:
                edge["status"] = other["status"]
    return out


@pytest.mark.parametrize("point, line", [("feb2025-1500", "R239"), ("nov2026-2000", "R001")])
def test_the_committed_cache_matches_the_engine_for_a_single_cut(sim, point, line):
    """The web reads the cache for one cut and this service for several: they must agree (regenerate with cascadasen-cache).

    One tolerance: an edge whose rounded loading is exactly 1.0 may be `ok` in one side and `overload` in the
    other. The engine decides with `ratio > 1.0` (domain/cascade/engine.py `_frame`), so last-bit BLAS/platform
    float noise flips it. Everything else must be equal.
    """
    cached = json.loads((REPO_ROOT / f"web/public/cache/{point}/{line}.json").read_text())
    live = sim.simulate_workflow(point, [line], [])["timeline"]
    assert _without_boundary_status(live, cached) == cached


def test_cost_endpoint_gives_the_25f_of_the_isci_study_and_a_cost_per_hour():
    """[44] ISCI for Enel Foundation: 81,430 MWh not served and about US$ 984 M for the 25F."""
    client = TestClient(create_app(settings=Settings(data_dir=REPO_ROOT / "data")))
    out = client.post("/api/v1/grids/cost", json={"point": POINT, "open_lines": ["R239"]}).json()
    assert out["cost_usd"] == pytest.approx(984e6, rel=0.01)
    assert out["energy_not_served_mwh"] == pytest.approx(81430, rel=0.01)
    assert out["cost_per_hour_usd"] == pytest.approx(out["cost_usd"] / 7.34, rel=0.01)
    night = client.post("/api/v1/grids/cost", json={"point": "feb2025-0300", "open_lines": ["R239"]}).json()
    assert night["breakdown"]["dark_mw"] == 0 and night["outage_hours"]["value"] == 1.0  # load shedding only
    assert client.post("/api/v1/grids/cost", json={"point": POINT}).json()["cost_usd"] == 0
    assert client.post("/api/v1/grids/cost", json={"point": "x"}).status_code == 404
