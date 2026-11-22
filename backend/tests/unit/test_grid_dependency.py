"""Heat maps on the grid as it stands after the user's changes (application/grid_dependency.py)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.application.grid_dependency import GridDependency
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


def test_unknown_point_is_not_found(dep):
    with pytest.raises(GridError) as exc:
        dep.dependency_workflow("nope", [], [])
    assert exc.value.kind == "not_found"


def test_api_dependency():
    client = TestClient(create_app(settings=Settings(data_dir=REPO_ROOT / "data")))
    ok = client.post("/api/v1/grids/dependency", json={"point": POINT})
    assert ok.status_code == 200 and ok.json()["nodes"]
    assert (
        client.post("/api/v1/grids/dependency", json={"point": POINT, "open_lines": ["R999"]}).status_code
        == 404
    )
