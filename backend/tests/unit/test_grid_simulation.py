"""Several edits at once, without a session (application/grid_simulation.py)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.application.grid_simulation import GridSimulator
from cascadasen.application.grids import GridError
from cascadasen.application.theater_world import default_world
from cascadasen.domain.cascade.engine import run_cascade_workflow
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
    assert out["timeline"] == run_cascade_workflow(net.buses, op, ["R001", "R239"])
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
