"""Optional LLM commander: it only picks among validated COAs, never sees the real state, falls
back to the rules on any failure, and a replay reuses its recorded picks without calling it."""

from types import SimpleNamespace

from cascadasen.domain.theater.cycle import AdversaryConfig, RunConfig, Simulation
from cascadasen.infrastructure.llm import ClaudeCommander, ClaudeInterpreter
from cascadasen.infrastructure.settings import Settings

ADV = AdversaryConfig(True, "pressure_resources", 12, True)


class FirstOnly:
    """Fake advisor: picks the first option each time and records what it was shown."""

    def __init__(self):
        self.calls = []

    def choose(self, context, options, capacity):
        self.calls.append((context, options, capacity))
        return {"chosen": [options[0]["id"]], "explanation": "Primero lo más urgente."}


class Broken:
    def choose(self, context, options, capacity):
        return None


def _run(net, advisor, **kw):
    sim = Simulation(
        net,
        RunConfig(template="open_field", seed=9, horizon=14, adversary=ADV, llm_commander=True, **kw),
        advisor=advisor,
    )
    sim.run_to_end()
    return sim


def test_llm_picks_at_most_one_and_is_audited(toy_world):
    adv = FirstOnly()
    sim = _run(toy_world, adv)
    assert adv.calls
    for s in sim.snapshots:
        assert sum(d["approved"] for d in s["decisions"]) <= 1
    entries = [e for e in sim.log.entries if e["kind"] == "llm_choice"]
    assert entries and entries[0]["payload"]["explanation"]
    context, options, _ = adv.calls[0]
    assert "real" not in context and all("id" in o for o in options)
    assert sim.log.verify()


def test_replay_uses_recorded_picks_without_calling_the_llm(toy_world):
    first = _run(toy_world, FirstOnly())
    again_adv = FirstOnly()
    again = _run(toy_world, again_adv, llm_choices=tuple(sorted(first.llm_record.items())))
    assert again_adv.calls == []
    assert [s["decisions"] for s in again.snapshots] == [s["decisions"] for s in first.snapshots]


def test_failure_falls_back_to_the_rules(toy_world):
    rules = Simulation(toy_world, RunConfig(template="open_field", seed=9, horizon=14, adversary=ADV))
    rules.run_to_end()
    broken = _run(toy_world, Broken())
    assert [s["decisions"] for s in broken.snapshots] == [s["decisions"] for s in rules.snapshots]


class FakeClient:
    def __init__(self, text, stop="end_turn"):
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.text, self.stop, self.kwargs = text, stop, None

    def _create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(stop_reason=self.stop, content=[SimpleNamespace(type="text", text=self.text)])


def test_claude_commander_parses_json_and_handles_refusal():
    ok = FakeClient('{"chosen": ["backup_comms:A09"], "explanation": "Recuperar visibilidad."}')
    out = ClaudeCommander(Settings(), client=ok).choose({}, [{"id": "backup_comms:A09"}], 1)
    assert out["chosen"] == ["backup_comms:A09"]
    assert ok.kwargs["model"] == "claude-opus-5-5" and ok.kwargs["fallbacks"] == "default"
    assert ClaudeCommander(Settings(), client=FakeClient("{}", stop="refusal")).choose({}, [], 1) is None
    assert ClaudeCommander(Settings(), client=FakeClient("not json")).choose({}, [], 1) is None


def test_claude_interpreter_keeps_the_template_on_failure(toy_world):
    sim = Simulation(toy_world, RunConfig(template="open_field", seed=2, horizon=4))
    sim.run_to_end()
    out = ClaudeInterpreter(Settings(), client=FakeClient("oops")).after_action(sim.report(), sim.snapshots)
    assert out["interpreter"] == "template" and out["summary"]
    good = ClaudeInterpreter(Settings(), client=FakeClient('{"narrative": "La organización resistió."}'))
    assert good.after_action(sim.report(), sim.snapshots)["narrative"] == "La organización resistió."
