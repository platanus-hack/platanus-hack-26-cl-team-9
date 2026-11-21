"""Field crews on the map: travel grows with distance, crews stay where they worked, the roster
never sends a crew that would arrive too late, and on-site actions wait for the crew."""

import random

from cascadasen.domain.theater.crews import CrewRoster, travel_table
from cascadasen.domain.theater.cycle import RunConfig, Simulation

PARAMS = {
    "bases": ["T1"],
    "mobilisation_cycles": 2,
    "road_speed_kmh": 90,
    "road_factor": 1.25,
    "travel_sigma": 0.0,
    "max_eta_cycles": 1000,
}


def test_travel_grows_with_distance(toy_world):
    t = travel_table(toy_world.network, PARAMS, 5)
    assert t[("T1", "T1")] == 2  # only mobilisation inside the area
    assert t[("T1", "T1")] < t[("T1", "T2")] < t[("T1", "T3")]


def test_a_freed_crew_leaves_from_where_it_worked(toy_world):
    roster = CrewRoster.build(toy_world.network, 1, PARAMS, 5)
    job = roster.dispatch(["T3"], "restore_element:T3", now=0)
    assert job and job.site == "T3"
    roster.sync(job.arrival, held=set())  # the ledger released the repair
    crew = roster.crews[0]
    assert crew.position == "T3" and crew.task is None
    assert roster.best_eta("T3") == 2


def test_timed_tasks_end_on_their_own_and_far_crews_are_not_sent(toy_world):
    roster = CrewRoster.build(toy_world.network, 1, {**PARAMS, "max_eta_cycles": 3}, 5)
    assert roster.dispatch(["T3"], "field_verification:T3", now=0) is None  # too far
    job = roster.dispatch(["T1"], "field_verification:T1", now=0, work=1)
    assert job.arrival == 2
    roster.sync(2, held={"field_verification:T1"})
    assert roster.crews[0].task is not None
    roster.sync(3, held={"field_verification:T1"})  # same key reused by a later action: still freed
    assert roster.crews[0].task is None


def test_travel_spread_comes_from_the_field_stream(toy_world):
    a = CrewRoster.build(toy_world.network, 1, {**PARAMS, "travel_sigma": 0.3}, 5, rng=random.Random(1))
    b = CrewRoster.build(toy_world.network, 1, {**PARAMS, "travel_sigma": 0.3}, 5, rng=random.Random(1))
    assert a.dispatch(["T3"], "x", 0).arrival == b.dispatch(["T3"], "x", 0).arrival


def test_runs_expose_crews_and_reports_arrive_with_the_crew(toy_world):
    sim = Simulation(toy_world, RunConfig(template="open_field", seed=4, horizon=6))
    sim.run_to_end()
    snap = sim.snapshots[-1]
    assert len(snap["crews"]) == int(sim.ledger.capacity["field_crews"])
    assert all({"id", "base", "position", "status"} <= set(c) for c in snap["crews"])
    for s in sim.snapshots:
        for e in s["executed"]:
            if e.get("crew"):
                assert e["arrival"] > s["cycle"]
