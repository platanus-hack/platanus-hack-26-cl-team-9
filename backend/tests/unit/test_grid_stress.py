"""Prepared scenarios (application/grid_stress.py, docs/stress.md): `/grids/prepare` only prepares the grid; the
failure runs in the existing simulation with the same `changes`."""

from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.application.grid_dependency import GridDependency
from cascadasen.application.grid_simulation import GridSimulator
from cascadasen.application.grid_stress import TECH_ORDER, _context, _floored, prepare_workflow
from cascadasen.application.grids import GridError
from cascadasen.application.theater_world import default_world
from cascadasen.infrastructure.settings import REPO_ROOT, Settings

PROCESSED = REPO_ROOT / "data/processed"
pytestmark = pytest.mark.skipif(not (PROCESSED / "grid_snapshot.json").exists(), reason="no processed data")
POINT = "feb2025-1500"
PUENTE_ALTO_X3 = [{"target": "population", "comunas": ["13201"], "factor": 3}]


@pytest.fixture(scope="module")
def world():
    return default_world(str(PROCESSED))


@pytest.fixture(scope="module")
def sim(world):
    return GridSimulator(world)


def test_population_adds_demand_at_the_per_capita_value(world):
    out = prepare_workflow(
        world, POINT, [{"target": "population", "comunas": ["Puente Alto"], "factor": 1.01}]
    )
    change, w = out["changes"][0], out["per_capita_w"]
    assert 200 < w < 260  # 38.9 % of 11,096 MW over 18.2 M people
    assert change["load_delta_mw"] == pytest.approx(change["people_delta"] * w / 1e6, abs=0.1)


def test_prepare_does_not_simulate(world):
    out = prepare_workflow(world, POINT, PUENTE_ALTO_X3)
    assert "timeline" not in out and "supply" not in out
    assert out["overloaded_lines"]  # the prepared grid already loads lines over their limit
    fed = out["should_feed"]["sources"]
    assert fed and all(r["pct_fed"] == 100.0 for r in fed)  # no failure: every source feeds whom it should


def test_the_failure_runs_in_the_simulation_on_the_prepared_grid(sim):
    base = sim.simulate_workflow(POINT, [], ["B020"])
    stressed = sim.simulate_workflow(POINT, [], ["B020"], PUENTE_ALTO_X3)
    assert (
        stressed["timeline"]["summary"]["people_without_power"]
        > base["timeline"]["summary"]["people_without_power"]
    )
    supply = stressed["supply"]
    assert any(r["pct_fed"] < 100 for r in supply["sources"])
    assert [r["id"] for r in supply["sources"]] == sorted(
        r["id"] for r in supply["sources"]
    )  # never by damage
    assert set(supply["by_zone"]) <= {"NG", "NC", "CE", "CS", "SU"}


def test_simulation_still_needs_a_failure(sim):
    with pytest.raises(GridError) as exc:
        sim.simulate_workflow(POINT, [], [], PUENTE_ALTO_X3)
    assert exc.value.kind == "invalid"


def test_dependency_keeps_scenarios_apart(world):
    dep = GridDependency(world)
    assert dep.dependency_workflow(POINT, [], [], PUENTE_ALTO_X3) is not dep.dependency_workflow(
        POINT, [], []
    )


def test_hydro_filter_moves_only_hydro_and_the_island_redispatches(world):
    ctx = _context(world, "feb2025-0300")
    hydro = float((ctx.op.gen * ctx.tech_share[:, TECH_ORDER.index("hidro")]).sum())
    out = prepare_workflow(
        world, "feb2025-0300", [{"target": "generation", "tech": ["hidro"], "factor": 0.5}]
    )
    assert out["changes"][0]["gen_delta_mw"] == pytest.approx(-hydro / 2, rel=0.01)
    assert out["totals"]["gen_total_mw"] == pytest.approx(
        float(ctx.op.gen.sum()), abs=1
    )  # the island compensates


def test_thermal_tag_is_coal_gas_and_diesel(world):
    def delta(tech):
        change = {"target": "generation", "tech": tech, "factor": 0}
        return prepare_workflow(world, "feb2025-0300", [change])["changes"][0]["gen_delta_mw"]

    assert delta(["termica"]) == pytest.approx(sum(delta([t]) for t in ("carbon", "gas", "diesel")), abs=0.5)


def test_unknown_filters_are_errors(world):
    for change, kind in (
        ({"target": "population", "comunas": ["Atlantis"], "factor": 2}, "not_found"),
        ({"target": "generation", "tech": ["nuclear"], "factor": 2}, "invalid"),
        ({"target": "lines", "lines": ["R999"], "factor": 2}, "not_found"),
    ):
        with pytest.raises(GridError) as exc:
            prepare_workflow(world, POINT, [change])
        assert exc.value.kind == kind


def test_floor_keeps_negative_base_values():
    out = _floored(np.array([-2.0, 5.0, 1.0]), np.array([-1.0, -10.0, 0.0]))
    assert out.tolist() == [-2.0, 0.0, 1.0]


def test_api_prepare_and_simulate_with_changes():
    client = TestClient(create_app(settings=Settings(data_dir=REPO_ROOT / "data")))
    changes = [{"target": "lines", "kv": [220], "factor": 0.9}]
    assert client.post("/api/v1/grids/prepare", json={"point": POINT, "changes": changes}).status_code == 200
    sim = client.post(
        "/api/v1/grids/simulate", json={"point": POINT, "open_lines": ["R239"], "changes": changes}
    )
    assert sim.status_code == 200 and "supply" in sim.json()
    both = {"point": POINT, "changes": [{"target": "demand", "factor": 2, "add": 1}]}
    assert client.post("/api/v1/grids/prepare", json=both).status_code == 422
    too_much = {"point": POINT, "changes": [{"target": "demand", "factor": 5}]}
    assert (
        client.post("/api/v1/grids/prepare", json=too_much).status_code == 422
    )  # over the overlay's MW limit


def test_a_line_with_no_capacity_is_a_failure_not_a_change(world):
    """The assistant sent open_lines R239 plus a lines change with factor 0, and the overlay answered only "Debe
    ser mayor que 0". Both the schema and the workflow now say to use open_lines."""
    with pytest.raises(GridError, match="open_lines") as exc:
        prepare_workflow(world, POINT, [{"target": "lines", "lines": ["R239"], "factor": 0}])
    assert exc.value.kind == "invalid"
    client = TestClient(create_app(settings=Settings(data_dir=REPO_ROOT / "data")))
    zero = {
        "point": POINT,
        "open_lines": ["R239"],
        "changes": [{"target": "lines", "lines": ["R239"], "factor": 0}],
    }
    answer = client.post("/api/v1/grids/simulate", json=zero)
    assert answer.status_code == 422 and "open_lines" in str(answer.json()["detail"])


VALLENAR_SOLAR = {
    "target": "substation",
    "places": ["Vallenar"],
    "name": "S/E Solar Vallenar",
    "generator_mw": 120,
    "tech": ["solar"],
}


def test_a_new_substation_joins_the_prepared_grid_with_its_lines_and_plant(world):
    out = prepare_workflow(world, POINT, [VALLENAR_SOLAR])
    row = out["changes"][0]
    assert row["new_substation"] and row["gen_mw"] == 120
    new = row["elements"][0]
    assert new["id"] == "B188" and new["name"] == "S/E Solar Vallenar" and new["lat"] and new["lon"]
    assert 1 <= len(row["connects_to"]) <= 2 and row["places"][0]["bus"] in row["connects_to"]
    plant = next(
        r for r in out["should_feed"]["sources"] if r["id"] == "B188"
    )  # the island redispatches the rest
    assert plant["name"] == "S/E Solar Vallenar" and plant["gen_mw"][0] == 120 and plant["zone"] == "NC"


def test_a_failure_runs_on_a_grid_with_a_new_substation(sim):
    out = sim.simulate_workflow(POINT, [], ["B105"], [VALLENAR_SOLAR])
    without = sim.simulate_workflow(POINT, [], ["B105"])
    assert out["timeline"]["summary"]["people_without_power"] >= 0
    assert out["supply"]["by_zone"] and without["supply"]["by_zone"]


def test_the_limit_of_new_substations_and_a_wrong_target_are_rejected(world):
    with pytest.raises(GridError, match="Máximo 5 subestaciones"):
        prepare_workflow(world, POINT, [VALLENAR_SOLAR] * 6)
    with pytest.raises(GridError):
        prepare_workflow(world, POINT, [{**VALLENAR_SOLAR, "places": ["Narnia"]}])


def test_api_prepare_and_simulate_with_a_new_substation():
    client = TestClient(create_app(settings=Settings(data_dir=REPO_ROOT / "data")))
    prep = client.post("/api/v1/grids/prepare", json={"point": POINT, "changes": [VALLENAR_SOLAR]})
    assert prep.status_code == 200 and prep.json()["changes"][0]["elements"][0]["id"] == "B188"
    sim = client.post(
        "/api/v1/grids/simulate", json={"point": POINT, "out_buses": ["B105"], "changes": [VALLENAR_SOLAR]}
    )
    assert sim.status_code == 200 and "supply" in sim.json()
    no_tech = {**VALLENAR_SOLAR, "tech": []}
    assert (
        client.post("/api/v1/grids/prepare", json={"point": POINT, "changes": [no_tech]}).status_code == 422
    )
    other = {"target": "demand", "add": 5, "name": "x"}
    assert client.post("/api/v1/grids/prepare", json={"point": POINT, "changes": [other]}).status_code == 422
