"""Strategic layer guarantees: information separation, determinism, read-only auditor, inviolable
validator, abstract-only adversary, audit chain, digital engine and resources (docs/strategy.md)."""

import dataclasses

import pytest

from cascadasen.domain.agents.auditor import AuditorAgent
from cascadasen.domain.simulation.grid import GridState
from cascadasen.domain.theater.audit import AuditLog
from cascadasen.domain.theater.config import theater_config
from cascadasen.domain.theater.cycle import (
    AdversaryConfig,
    RunConfig,
    RunFinishedError,
    RunInputError,
    Simulation,
)
from cascadasen.domain.theater.decisions import COA
from cascadasen.domain.theater.resources import Ledger
from cascadasen.domain.theater.state import AreaDigital, Effect, RealState
from cascadasen.domain.theater.validator import ValidationContext, validate

FORBIDDEN = (RealState, GridState, AreaDigital, Effect)


def _sim(net, **kw):
    base = dict(template="open_field", seed=3, horizon=10)
    base.update(kw)
    return Simulation(net, RunConfig(**base))


def _reachable(obj, seen=None):
    seen = seen if seen is not None else set()
    if id(obj) in seen:
        return
    seen.add(id(obj))
    yield obj
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        for f in dataclasses.fields(obj):
            yield from _reachable(getattr(obj, f.name), seen)
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _reachable(v, seen)
    elif isinstance(obj, list | tuple | set | frozenset):
        for v in obj:
            yield from _reachable(v, seen)


def test_no_agent_view_reaches_the_real_state(toy_world):
    sim = _sim(toy_world, adversary=AdversaryConfig(True, "reduce_observability", 6, True))
    sim.inject("D4_comms_loss", "T2")
    sim.step(3)
    obs = sim.observations[-1]
    views = [sim._view("isr", obs, ()), sim._view("c2", obs, (), isr=sim.isr.report)]
    for v in views:
        assert not [o for o in _reachable(v) if isinstance(o, FORBIDDEN)]
    assert not [o for o in _reachable(sim._adversary_view()) if isinstance(o, FORBIDDEN)]


def test_same_recipe_same_trace_and_different_policy_differs(toy_world):
    def run(policy):
        sim = _sim(toy_world, policy=policy, adversary=AdversaryConfig(True, "raise_uncertainty", 6, True))
        sim.inject("C3_transmission_opening", "T2-T3", cause="intentional")
        sim.step(4)
        sim.inject("D3_unreliable_data", "SE_C1")
        sim.run_to_end()
        return sim

    a, b = run("C"), run("C")
    assert a.log.head == b.log.head and a.log.verify()
    assert run("B").log.head != a.log.head


def test_audit_chain_detects_tampering():
    log = AuditLog()
    for k in range(3):
        log.append(k, "plan", "staff", "proposals", {"n": k, "x": 0.1 + k})
    assert log.verify()
    log.entries[1]["payload"]["n"] = 99
    assert not log.verify()


def test_auditor_has_no_write_path(toy_world):
    fields = {f.name for f in dataclasses.fields(AuditorAgent)}
    assert not fields & {"log", "sim", "real", "ledger", "executor"}
    sim = _sim(toy_world)
    sim.inject("D1_telemetry_loss", "T1")
    sim.step(2)
    assert any(e["actor"] == "auditor" and e["kind"] == "findings" for e in sim.log.entries)


def _ctx(sim, **kw):
    return ValidationContext(
        sim.network,
        sim.real,
        sim.ledger,
        sim.mission,
        None,
        sim.cfg.actions,
        sim.defense_areas,
        **kw,
    )


def test_validator_is_inviolable(toy_world):
    sim = _sim(toy_world)
    ctx = _ctx(sim)
    assert validate(COA("preventive_load_reduction", "T2", "operations", "x"), ctx).code == "not_permitted"
    sim.real.digital["T2"].comms = "down"
    assert (
        validate(COA("fast_reserve", "T2", "stabilization", "x"), ctx).code
        == "remote_command_not_acknowledged"
    )
    poor = _ctx(sim)
    poor.ledger = Ledger({"field_crews": 0})
    assert validate(COA("manual_operation", "T1", "operations", "x"), poor).code == "insufficient_resources"
    assert validate(COA("restore_element", "T1", "operations", "x"), ctx).code == "nothing_to_restore"


def test_digital_engine_perfect_information_and_comms_loss(toy_world):
    perfect = _sim(toy_world, uncertainty=0.0)
    perfect.inject("D4_comms_loss", "T2")
    perfect.step(1)
    obs = perfect.observations[-1]
    assert all(a.served_mw == pytest.approx(perfect.real.grid.served_mw[a.area]) for a in obs.areas)
    base = _sim(toy_world, uncertainty=1.0)
    base.inject("D4_comms_loss", "T2")
    base.step(1)
    o = base.observations[-1]
    assert o.area("T2").served_mw is None and any(x.kind == "comms_lost" for x in o.alarms_in("T2"))


def test_unreliable_data_looks_normal(toy_world):
    sim = _sim(toy_world, uncertainty=1.0)
    sim.inject("D3_unreliable_data", "T3")
    sim.step(1)
    real = sim.real.grid.served_mw["T3"]
    seen = sim.observations[-1].area("T3").served_mw
    assert seen is not None and seen != pytest.approx(real, rel=1e-3)  # frozen and biased, not missing


def test_adversary_stays_in_the_abstract_catalog_and_adapts(toy_world):
    cfg = theater_config()

    def run(policy):
        sim = _sim(
            toy_world,
            policy=policy,
            horizon=20,
            adversary=AdversaryConfig(True, "pressure_resources", 12, True),
        )
        sim.run_to_end()
        return sim

    a, b = run("A"), run("B")
    allowed = set(cfg.adversary["objectives"]["pressure_resources"])
    for sim in (a, b):
        effects = [e for e in sim.real.effects if e.source == "adversary"]
        assert effects and all(e.event in allowed and e.area in toy_world.network.areas for e in effects)
        assert set(sim.report()["adversary"]["strategy_mix"]) <= allowed  # event types only, no areas
    assert a.adversary.weights != b.adversary.weights  # it learned differently against another defence


def test_perfect_information_has_no_estimation_gap(toy_world):
    sim = _sim(toy_world, uncertainty=0.0)
    sim.inject("C1_generation_loss", "T1", {"share": 0.5})
    sim.run_to_end()
    assert sim.report()["indicators"]["situational_awareness"]["mean_estimation_gap"] == pytest.approx(
        0, abs=1e-6
    )


def test_ledger_keeps_reserve_and_refills_attention():
    led = Ledger({"field_crews": 4, "operator_attention": 2})
    assert led.can_afford({"field_crews": 2}, keep=0.5)
    assert not led.can_afford({"field_crews": 3}, keep=0.5)
    led.spend({"field_crews": 1}, "a", release=2)
    led.spend({"operator_attention": 2}, "c2", None)
    assert led.available("operator_attention") == 0
    led.new_cycle(2)
    assert led.available("field_crews") == 4 and led.available("operator_attention") == 2


def test_run_input_errors(toy_world):
    with pytest.raises(RunInputError) as e:
        _sim(toy_world, template="nope")
    assert e.value.not_found
    with pytest.raises(RunInputError):
        _sim(toy_world, policy="Z")
    sim = _sim(toy_world, horizon=1)
    with pytest.raises(RunInputError) as e:
        sim.inject("D1_telemetry_loss", "NOPE")
    assert e.value.not_found
    sim.run_to_end()
    with pytest.raises(RunFinishedError):
        sim.inject("D1_telemetry_loss", "T1")


def test_adversary_with_defence_events_runs_and_stays_abstract(toy_world):
    """complicate_recovery includes C4 (defence not acting): its arms target defence functions,
    never an area id, and the run completes for every seed."""
    for seed in range(10):
        sim = _sim(
            toy_world,
            seed=seed,
            horizon=16,
            adversary=AdversaryConfig(True, "complicate_recovery", 12, True),
        )
        sim.run_to_end()
        kinds = {t for ev, t in sim.adversary.arms if ev == "C4_defense_not_acting"}
        assert kinds and kinds <= set(sim.defense_areas)
        for e in (e for e in sim.real.effects if e.source == "adversary"):
            assert (
                e.target in toy_world.network.areas
                or e.target in sim.defense_areas
                or e.target in toy_world.network.zones
            )


def test_run_without_seed_gets_a_recorded_random_seed(toy_world):
    a = Simulation(toy_world, RunConfig(template="open_field", horizon=3))
    b = Simulation(toy_world, RunConfig(template="open_field", horizon=3))
    assert isinstance(a.config.seed, int) and a.config.seed != b.config.seed
    assert a.log.entries[0]["payload"]["config"]["seed"] == a.config.seed  # in the recipe
    again = Simulation(toy_world, RunConfig(template="open_field", horizon=3, seed=a.config.seed))
    a.run_to_end()
    again.run_to_end()
    assert a.log.head == again.log.head
