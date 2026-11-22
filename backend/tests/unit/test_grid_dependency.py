"""Heat maps on the grid as it stands after the user's changes (application/grid_dependency.py)."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.application.grid_dependency import DISASTERS, GridDependency
from cascadasen.application.grids import GridError
from cascadasen.application.theater_world import default_world
from cascadasen.infrastructure.settings import REPO_ROOT, Settings

PROCESSED = REPO_ROOT / "data/processed"
pytestmark = pytest.mark.skipif(not (PROCESSED / "grid_snapshot.json").exists(), reason="no processed data")
POINT = (
    "feb2025-0300"  # the 25F cut does not black the country out at night, so there is a grid left to measure
)


@pytest.fixture(scope="module")
def dep() -> GridDependency:
    return GridDependency(default_world(str(PROCESSED)))


def test_base_case_scores_every_substation_and_feeds_the_people(dep):
    out = dep.dependency_workflow(POINT, [], [])
    assert out["open_lines"] == [] and len(out["nodes"]) > 150
    assert all(0.0 <= n["criticality"] <= 1.0 for n in out["nodes"].values())
    assert sum(n["people_fed"] for n in out["nodes"].values()) > 0


def test_changes_are_applied_before_measuring(dep):
    base = dep.dependency_workflow(POINT, [], [])
    cut = dep.dependency_workflow(POINT, ["R239"], [])
    assert "R239" in cut["open_lines"]  # the user's cut plus what its cascade opened
    assert cut["nodes"] != base["nodes"]
    out = dep.dependency_workflow(POINT, [], ["B020"])
    assert "B020" not in out["nodes"]  # a substation out of service has no line left to score


def test_results_are_kept_for_the_same_changes(dep):
    assert dep.dependency_workflow(POINT, ["R239"], []) is dep.dependency_workflow(POINT, ["R239"], [])


def test_without_criticality_feeds_the_same_people(dep):
    # Dependencia asks with criticality=False: same people, same substations, no criticality cascades
    for cuts in ([], ["R239"]):
        full = dep.dependency_workflow(POINT, cuts, [])
        light = dep.dependency_workflow(POINT, cuts, [], criticality=False)
        assert light["open_lines"] == full["open_lines"]
        assert light["nodes"].keys() == full["nodes"].keys()
        for bus, node in light["nodes"].items():
            assert set(node) == {"gen_mw", "people_fed", "share_of_people"}
            assert {k: full["nodes"][bus][k] for k in node} == node


def test_unknown_point_is_not_found(dep):
    with pytest.raises(GridError) as exc:
        dep.dependency_workflow("nope", [], [])
    assert exc.value.kind == "not_found"


def test_api_dependency():
    client = TestClient(create_app(settings=Settings(data_dir=REPO_ROOT / "data")))
    ok = client.post("/api/v1/grids/dependency", json={"point": POINT})
    assert ok.status_code == 200 and ok.json()["nodes"]
    light = client.post("/api/v1/grids/dependency", json={"point": POINT, "criticality": False})
    assert light.status_code == 200
    assert all(
        n["people_fed"] == ok.json()["nodes"][k]["people_fed"]
        and n["share_of_people"] == ok.json()["nodes"][k]["share_of_people"]
        and "criticality" not in n
        for k, n in light.json()["nodes"].items()
    )
    assert (
        client.post("/api/v1/grids/dependency", json={"point": POINT, "open_lines": ["R999"]}).status_code
        == 404
    )


def test_startup_warms_the_base_hours_and_the_disasters_while_health_answers():
    app = create_app(settings=Settings(data_dir=REPO_ROOT / "data"))
    with TestClient(app) as client:  # the context runs the lifespan, which starts the warm-up thread
        warm = next(t for t in threading.enumerate() if t.name == "warm-dependency")
        assert client.get("/api/v1/health").status_code == 200  # answers while the warm-up runs
        assert warm.is_alive()
        warm.join(timeout=120)
        assert not warm.is_alive()
        service = app.state.grid_dependency
        assert len(service._cache) == len(service.world.points()) + len(DISASTERS)
        before = client.post(
            "/api/v1/grids/dependency", json={"point": "nov2026-2000", "out_buses": ["B043"]}
        )
        assert before.status_code == 200 and len(service._cache) == len(service.world.points()) + len(
            DISASTERS
        )


def test_the_warm_up_can_be_turned_off():
    app = create_app(settings=Settings(data_dir=REPO_ROOT / "data", warm_dependency=False))
    with TestClient(app):
        assert app.state.grid_dependency is None
