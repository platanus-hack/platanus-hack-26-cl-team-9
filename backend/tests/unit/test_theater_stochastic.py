"""Chance in the theatre: sampled sizes, unplanned events, failing actions, independent streams."""

import pytest

from cascadasen.domain.theater.config import theater_config
from cascadasen.domain.theater.cycle import AdversaryConfig, RunConfig, Simulation
from cascadasen.domain.theater.stochastic import Chance


def _chance(seed=1):
    return Chance.for_run(seed, theater_config().stochastic)


def test_sampled_share_centres_on_the_catalog_default_and_explicit_values_stay_exact():
    ch = _chance()
    shares = [ch.effect_params({"share": 0.25}, {})["share"] for _ in range(2000)]
    assert sum(shares) / len(shares) == pytest.approx(0.25, abs=0.01)
    assert len(set(shares)) > 100  # it really varies
    assert ch.effect_params({"share": 0.25, "mw": 300}, {"mw": 450})["mw"] == 450


def test_actions_fail_at_the_configured_rate():
    ch = _chance()
    p = theater_config().stochastic["action_success_p"]["rearm_defense"]
    ok = sum(ch.action_succeeds("rearm_defense") for _ in range(4000)) / 4000
    assert ok == pytest.approx(p, abs=0.03)
    assert all(ch.action_succeeds("isr_tasking") for _ in range(100))  # not listed: always works


def _external(sim):
    return [
        (e.start, e.event, e.target, tuple(sorted(e.params.items())))
        for e in sim.real.effects
        if e.source == "external"
    ]


def test_the_world_has_the_same_luck_under_any_policy(toy_network):
    runs = {}
    for policy in ("A", "B"):
        sim = Simulation(toy_network, RunConfig(template="open_field", policy=policy, seed=11, horizon=40))
        sim.run_to_end()
        runs[policy] = sim
    assert _external(runs["A"])  # unplanned events happen
    assert _external(runs["A"]) == _external(runs["B"])


def test_different_seeds_give_different_runs(toy_network):
    adv = AdversaryConfig(True, "reduce_observability", 8, True)
    heads = set()
    for seed in (1, 2, 3):
        sim = Simulation(toy_network, RunConfig(template="open_field", seed=seed, horizon=20, adversary=adv))
        sim.run_to_end()
        heads.add(sim.log.head)
    assert len(heads) == 3


def test_stochastic_off_keeps_catalog_sizes_and_no_unplanned_events(toy_network):
    sim = Simulation(
        toy_network,
        RunConfig(
            template="open_field",
            seed=5,
            horizon=30,
            stochastic=False,
            adversary=AdversaryConfig(True, "complicate_recovery", 10, True),
        ),
    )
    sim.run_to_end()
    assert sim.chance is None and not _external(sim)
    defaults = theater_config().effects
    for e in sim.real.effects:
        if "share" in (defaults.get(e.event) or {}):
            assert e.params["share"] == defaults[e.event]["share"]
