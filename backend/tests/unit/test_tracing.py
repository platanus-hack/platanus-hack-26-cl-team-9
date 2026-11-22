"""Proportional sharing of the base-case flow: who feeds whom."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from cascadasen.domain.cascade.flow import dc_flow, find_islands
from cascadasen.domain.cascade.network import Line, ReducedNetwork
from cascadasen.domain.cascade.scenario import load_network_and_point
from cascadasen.domain.cascade.tracing import dependency_workflow, generation_shares

PROCESSED = Path(__file__).resolve().parents[3] / "data" / "processed"


def _toy_net() -> ReducedNetwork:
    """A(0) - B(1), A - C(2), B - C. Equal reactances."""
    lines = [
        Line("R0", 0, 1, 200.0, 0.01, 220, ("ab",), ()),
        Line("R1", 0, 2, 200.0, 0.01, 220, ("ac",), ()),
        Line("R2", 1, 2, 100.0, 0.01, 220, ("bc",), ()),
    ]
    return ReducedNetwork(
        names=["A", "B", "C"],
        lat=[-33.0] * 3,
        lon=[-70.0] * 3,
        kv=[220.0] * 3,
        model_buses=[["A_220"], ["B_220"], ["C_220"]],
        map_nodes=[[], [], []],
        lines=lines,
        index={"A": 0, "B": 1, "C": 2},
        bus_of_model_bus={"A_220": 0, "B_220": 1, "C_220": 2},
    )


def test_a_single_generator_feeds_every_person():
    net = _toy_net()
    rows = dependency_workflow(
        net, np.array([300.0, 0, 0]), np.array([0.0, 100, 200]), np.array([0.0, 1000, 3000])
    )
    assert [r["bus"] for r in rows] == ["B000"]
    assert rows[0]["people_fed"] == 4000
    assert rows[0]["share_of_people"] == 1.0


def test_two_generators_share_what_they_feed_and_nothing_is_lost():
    net = _toy_net()
    gen, load, people = (
        np.array([200.0, 100.0, 0.0]),
        np.array([0.0, 0.0, 300.0]),
        np.array([0.0, 0.0, 9000.0]),
    )
    flows = dc_flow(net, set(), gen - load, find_islands(net, set()))
    c = generation_shares(net, gen, flows)
    assert np.allclose(c[2].sum(), 1.0)  # all the power at C comes from somebody
    assert (c >= -1e-9).all() and (c <= 1 + 1e-9).all()
    rows = {r["bus"]: r for r in dependency_workflow(net, gen, load, people)}
    assert abs(sum(r["people_fed"] for r in rows.values()) - 9000) <= 1  # rounding of two numbers
    assert rows["B000"]["people_fed"] > rows["B001"]["people_fed"]  # the bigger generator feeds more


def test_real_grid_feeds_almost_everybody():
    net, point = load_network_and_point(PROCESSED, "feb2025-1500")
    rows = dependency_workflow(net, point.gen, point.load, point.people)
    fed = sum(r["people_fed"] for r in rows)
    assert (
        0.98 * float(point.people.sum()) < fed <= float(point.people.sum()) + len(rows)
    )  # people at substations that no power crosses are not fed
    assert all(0.0 <= r["share_of_people"] <= 1.0 for r in rows)
