"""Optional LLM commander: it only picks among validated COAs, never sees the real state, falls
back to the rules on any failure, and a replay reuses its recorded picks without calling it."""

from types import SimpleNamespace

import pytest

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
    notes = [s["llm"] for s in sim.snapshots if s["llm"] and s["llm"]["status"] == "chosen"]
    assert notes and notes[0]["explanation"] == "Primero lo más urgente." and len(notes[0]["chosen"]) == 1
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


def _settings(**kw):
    """Settings that ignore the developer's backend/.env (it may enable Bedrock)."""
    return Settings(_env_file=None, **kw)


class FakeClient:
    def __init__(self, text, stop="end_turn"):
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))
        self.messages = SimpleNamespace(create=self._create)  # Bedrock path (no beta, no fallbacks)
        self.text, self.stop, self.kwargs = text, stop, None

    def _create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(stop_reason=self.stop, content=[SimpleNamespace(type="text", text=self.text)])


def test_claude_commander_parses_json_and_handles_refusal():
    ok = FakeClient('{"chosen": ["backup_comms:A09"], "explanation": "Recuperar visibilidad."}')
    out = ClaudeCommander(_settings(), client=ok).choose({}, [{"id": "backup_comms:A09"}], 1)
    assert out["chosen"] == ["backup_comms:A09"]
    assert ok.kwargs["model"] == "claude-opus-5-5" and ok.kwargs["fallbacks"] == "default"
    assert ClaudeCommander(_settings(), client=FakeClient("{}", stop="refusal")).choose({}, [], 1) is None
    assert ClaudeCommander(_settings(), client=FakeClient("not json")).choose({}, [], 1) is None


def test_claude_interpreter_keeps_the_template_on_failure(toy_world):
    sim = Simulation(toy_world, RunConfig(template="open_field", seed=2, horizon=4))
    sim.run_to_end()
    out = ClaudeInterpreter(_settings(), client=FakeClient("oops")).after_action(sim.report(), sim.snapshots)
    assert out["interpreter"] == "template" and out["summary"]
    good = ClaudeInterpreter(_settings(), client=FakeClient('{"narrative": "La organización resistió."}'))
    assert good.after_action(sim.report(), sim.snapshots)["narrative"] == "La organización resistió."


def test_bedrock_request_has_prefixed_model_and_no_fallbacks():
    client = FakeClient('{"chosen": ["backup_comms:A09"], "explanation": "Recuperar visibilidad."}')
    settings = _settings(llm_provider="bedrock", aws_region="us-east-1", aws_profile="cascadasen")
    out = ClaudeCommander(settings, client=client).choose({}, [{"id": "backup_comms:A09"}], 1)
    assert out["chosen"] == ["backup_comms:A09"]
    assert client.kwargs["model"] == "anthropic.claude-opus-5-5"
    assert "fallbacks" not in client.kwargs and "betas" not in client.kwargs
    assert client.kwargs["output_config"]["format"]["type"] == "json_schema"


def test_settings_read_the_provider_and_aws_profile_from_env_file(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "CASCADASEN_LLM_ENABLED=true\nCASCADASEN_LLM_PROVIDER=bedrock\n"
        "CASCADASEN_AWS_REGION=us-east-1\nCASCADASEN_AWS_PROFILE=cascadasen\n"
    )
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert (s.llm_enabled, s.llm_provider, s.aws_region, s.aws_profile) == (
        True,
        "bedrock",
        "us-east-1",
        "cascadasen",
    )


def test_bedrock_adapters_use_the_aws_profile(monkeypatch):
    anthropic = pytest.importorskip("anthropic")

    from cascadasen.infrastructure.llm import llm_adapters

    built = []

    class FakeMantle:
        def __init__(self, **kwargs):
            built.append(kwargs)

    monkeypatch.setattr(anthropic, "AnthropicBedrockMantle", FakeMantle)
    settings = _settings(
        llm_enabled=True, llm_provider="bedrock", aws_region="us-east-1", aws_profile="cascadasen"
    )
    interpreter, advisor = llm_adapters(settings)
    assert interpreter is not None and advisor is not None
    assert built and all(k["aws_profile"] == "cascadasen" and k["aws_region"] == "us-east-1" for k in built)


class ValidationException(Exception):
    pass


class FakeConverse:
    """Fake bedrock-runtime client: `forced` says whether the model accepts a forced tool call."""

    def __init__(self, forced=True, text='{"narrative": "La organización resistió."}'):
        self.forced, self.text, self.calls = forced, text, []

    def converse(self, **kw):
        self.calls.append(kw)
        if "toolConfig" in kw:
            if not self.forced:
                raise ValidationException("toolChoice not supported")
            return {
                "output": {
                    "message": {
                        "content": [
                            {
                                "toolUse": {
                                    "name": "responder",
                                    "input": {"chosen": ["x"], "explanation": "ok"},
                                }
                            }
                        ]
                    }
                }
            }
        return {"output": {"message": {"content": [{"text": "```json\n" + self.text + "\n```"}]}}}


def test_converse_uses_a_forced_tool_with_the_schema_and_the_model_id_as_is():
    client = FakeConverse()
    settings = _settings(llm_provider="bedrock-converse", llm_model="amazon.nova-pro-v1:0")
    out = ClaudeCommander(settings, client=client).choose({}, [{"id": "x"}], 1)
    assert out == {"chosen": ["x"], "explanation": "ok"}
    call = client.calls[0]
    assert call["modelId"] == "amazon.nova-pro-v1:0"
    assert call["toolConfig"]["tools"][0]["toolSpec"]["inputSchema"]["json"]["required"] == [
        "chosen",
        "explanation",
    ]


def test_converse_falls_back_to_the_schema_in_the_prompt():
    client = FakeConverse(forced=False)
    settings = _settings(llm_provider="bedrock-converse", llm_model="meta.llama3-3-70b-instruct-v1:0")
    out = ClaudeCommander(settings, client=client)._json("s", {}, {"type": "object"})
    assert out == {"narrative": "La organización resistió."}
    assert "toolConfig" not in client.calls[1] and "esquema" in client.calls[1]["system"][0]["text"]
