"""Ciberataque scenario (docs/attack-sim.md 3.2): the propagating intrusion on its own (unit, no grid),
and whole runs on the toy theatre and on the real network: seeded, area-level only, early end."""

import random

import pytest

from cascadasen.domain.agents.base import AdversaryView
from cascadasen.domain.agents.propagation import (
    PropagatingAdversary,
    PropagationParamError,
    propagation_params,
)
from cascadasen.domain.theater.config import theater_config
from cascadasen.domain.theater.cycle import AdversaryConfig, RunConfig, RunInputError, Simulation

LINE = {"A": ["B"], "B": ["A", "C"], "C": ["B"]}  # A - B - C
P = {**theater_config().cyber_attack, "spread_p": 1.0, "isolation_p": 1.0, "eradicate_p": 1.0}


def _view(cycle, posture=None, effects=()):
    return AdversaryView(cycle, 0.0, tuple((posture or {}).items()), tuple(effects), 1.0, ())


def _worm(**params):
    return PropagatingAdversary(LINE, {**P, **params}, random.Random(1))


def test_the_start_has_at_least_two_neighbours():
    worm = _worm()
    [req] = worm.act(_view(0))
    assert worm.start == "B" and req.type == "D4_comms_loss" and req.target == "B"


def test_it_spreads_to_neighbours_and_strikes_after_the_delay():
    worm = _worm(strike_delay=2, spread_cooldown=1)
    worm.act(_view(0))
    kinds = [(r.type, r.target) for r in worm.act(_view(1))]
    assert ("D4_comms_loss", "A") in kinds and ("D4_comms_loss", "C") in kinds
    struck = [(r.type, r.target) for r in worm.act(_view(2))]
    assert ("C5_remote_dispatch_loss", "B") in struck and ("C1_generation_loss", "B") in struck


def test_a_segmented_area_stops_the_jump():
    worm = _worm(spread_cooldown=1)
    worm.act(_view(0))
    reqs = worm.act(_view(1, {"B": "segmented"}))
    assert not [r for r in reqs if r.type == "D4_comms_loss"]
    assert {e["kind"] for e in worm.events} >= {"blocked"}


def test_segmentation_long_enough_eradicates_and_the_area_stays_clean():
    worm = _worm(clean_after_segmented=2)
    worm.act(_view(0))
    for cycle in (1, 2):
        worm.learn(_view(cycle, {"B": "segmented"}))
    assert worm.snapshot()["areas"]["B"] == "eradicated" and worm.active() == []


def test_parameters_are_bounded():
    assert propagation_params(P, {"spread_p": 0.2})["spread_p"] == 0.2
    for bad in ({"spread_p": 2}, {"unknown": 1}):
        with pytest.raises(PropagationParamError):
            propagation_params(P, bad)


def _sim(world, seed=3, **prop):
    adv = AdversaryConfig(
        enabled=True, mode="propagation", adaptive=False, budget=0, propagation=prop or None
    )
    return Simulation(world, RunConfig(template="ciberataque", seed=seed, adversary=adv))


def test_a_run_is_seeded_area_level_and_ends_with_an_outcome(toy_world):
    a, b = _sim(toy_world), _sim(toy_world)
    a.run_to_end()
    b.run_to_end()
    assert a.report()["cyber_attack"] == b.report()["cyber_attack"]
    report = a.report()["cyber_attack"]
    assert report["outcome"] in ("attack", "defense", "undecided") and report["is_assumption"] is True
    areas = set(toy_world.load("nov2026-1300")[0].areas)
    assert set(a.snapshots[-1]["cyber"]["areas"]) == areas
    targets = {e["target"] for s in a.snapshots for e in s["events"] if e["source"] == "adversary"}
    assert targets <= areas  # never a bus, line or corridor (cyber.md 8 item 7)


def test_the_attack_wins_when_the_lost_share_is_reached(toy_world):
    sim = _sim(
        toy_world,
        attack_win_lost_share=0.1,
        generation_share=1.0,
        strike_delay=0,
        spread_p=1,
        spread_cooldown=1,
        isolation_p=0,
    )
    sim.run_to_end()
    assert sim.outcome == "attack" and sim.cycle < sim.horizon


def test_bad_propagation_parameters_are_a_run_input_error(toy_world):
    with pytest.raises(RunInputError):
        _sim(toy_world, spread_p=5)


def test_the_api_runs_it_in_a_session_and_reports_it(toy_world, toy_spec):
    from fastapi.testclient import TestClient

    from cascadasen.api.app import create_app

    app = create_app()
    client = TestClient(app)
    catalog = client.get("/api/v1/sim/catalog")
    if catalog.status_code != 200:
        pytest.skip("no processed data")
    cyber = catalog.json()["cyber_attack"]
    assert cyber["template"] == "ciberataque" and "spread_p" in cyber["bounds"] and cyber["adjacency"]
    sid = client.post("/api/v1/sessions", json={}).json()["session_id"]
    body = {
        "template": "ciberataque",
        "seed": 2,
        "adversary": {
            "mode": "propagation",
            "adaptive": False,
            "budget": 0,
            "propagation": {"spread_p": 0.6},
        },
        "capabilities": {"field_crews": 4},
    }
    run = client.post(f"/api/v1/sessions/{sid}/runs", json=body)
    assert run.status_code == 201, run.text
    rid = run.json()["run_id"]
    step = client.post(f"/api/v1/sessions/{sid}/runs/{rid}/step", json={"cycles": 12}).json()
    assert all("cyber" in s for s in step["snapshots"])
    report = client.get(f"/api/v1/sessions/{sid}/runs/{rid}/report").json()
    assert report["cyber_attack"]["params"]["spread_p"] == 0.6
    bad = {**body, "adversary": {**body["adversary"], "propagation": {"spread_p": 3}}}
    assert client.post(f"/api/v1/sessions/{sid}/runs", json=bad).status_code == 422
