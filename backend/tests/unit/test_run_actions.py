"""External agent actions on a run (Simulation.submit_action) and the rebuildable recipe."""

import json

import pytest

from cascadasen.domain.theater.catalog import ACTIONS
from cascadasen.domain.theater.cycle import (
    AdversaryConfig,
    RunConfig,
    RunFinishedError,
    RunInputError,
    Simulation,
)


def _sim(world, **kw):
    return Simulation(world, RunConfig(**{"template": "open_field", "seed": 3, "horizon": 10, **kw}))


def test_restore_after_an_opening_runs_as_operations(toy_world):
    assert "operations" in {r.value for r in ACTIONS["restore_element"].proposers}
    sim = _sim(toy_world)
    sim.inject("C3_transmission_opening", "T2-T3", cause="intentional")
    sim.step(1)
    out = sim.submit_action("restore_element", "T2-T3", "operations", agent="bot-1")
    assert out["accepted"] and out["applies_at_cycle"] == 1
    snap = sim.step(1)[0]
    restores = [e for e in snap["executed"] if e["action"] == "restore_element" and e["target"] == "T2-T3"]
    assert len(restores) == 1 and restores[0]["proposer"] == "operations"
    # C2 approved the same restore itself, so the external one is not added twice
    assert sum(d["action"] == "restore_element" and d["target"] == "T2-T3" for d in snap["decisions"]) == 1
    assert sim.trace()["verified"]
    assert sim.recipe()["actions"] == [
        {
            "cycle": 1,
            "action": "restore_element",
            "target": "T2-T3",
            "role": "operations",
            "params": {},
            "agent": "bot-1",
            "after_events": 1,
        }
    ]


def test_an_action_c2_did_not_choose_is_executed_as_external(toy_world):
    sim = _sim(toy_world, stochastic=False)
    sim.submit_action("field_verification", "T1", "operations")
    snap = sim.step(1)[0]
    assert [(d["action"], d["reason"]) for d in snap["decisions"] if d["target"] == "T1"] == [
        ("field_verification", "external_agent")
    ]
    assert any(e["action"] == "field_verification" and e["ok"] for e in snap["executed"])
    assert any(e["kind"] == "action_queued" and e["actor"] == "external" for e in sim.log.entries)
    assert sim.trace()["verified"]


def test_structural_errors(toy_world):
    sim = _sim(toy_world)
    with pytest.raises(RunInputError) as exc:
        sim.submit_action("nope", "T1", "operations")
    assert exc.value.field == "action" and not exc.value.not_found
    with pytest.raises(RunInputError) as exc:
        sim.submit_action("restore_element", "T1", "isr")
    assert exc.value.field == "role" and exc.value.valid == ["operations"]
    with pytest.raises(RunInputError) as exc:
        sim.submit_action("restore_element", "T1", "not-a-role")
    assert exc.value.field == "role"
    with pytest.raises(RunInputError) as exc:
        sim.submit_action("restore_element", "NOPE", "operations")
    assert exc.value.field == "target" and exc.value.not_found
    assert sim.actions == [] and sim.action_queue == []


def test_finished_run_rejects_actions(toy_world):
    sim = _sim(toy_world, horizon=1)
    sim.run_to_end()
    with pytest.raises(RunFinishedError):
        sim.submit_action("field_verification", "T1", "operations")


def test_config_round_trips_through_json(toy_world):
    config = RunConfig(
        template="open_field",
        policy="A",
        seed=7,
        horizon=6,
        adversary=AdversaryConfig(True, "raise_uncertainty", 6, True),
        capabilities=(("field_crews", 4.0),),
        initial_events=({"type": "D4_comms_loss", "target": "T2", "cycle": 1},),
        llm_choices=((2, ("a:T1",)),),
    )
    assert RunConfig.from_dict(json.loads(json.dumps(config.as_dict()))) == config
    sim = _sim(toy_world)
    assert RunConfig.from_dict(sim.config.as_dict()) == sim.config


def test_runs_without_actions_keep_their_trace(toy_world):
    def run():
        sim = _sim(toy_world)
        sim.inject("C3_transmission_opening", "T2-T3", cause="intentional")
        sim.run_to_end()
        return sim

    a, b = run(), run()
    assert a.log.head == b.log.head and a.recipe()["actions"] == [] and a.recipe()["cycle"] == 10
