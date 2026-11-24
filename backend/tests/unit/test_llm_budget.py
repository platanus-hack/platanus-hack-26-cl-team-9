"""The global cap on Bedrock calls: the counter and its three call sites (assistant turn, commander,
interpreter). A refused call degrades like any other failure."""

import pytest

from cascadasen.domain.ports import ToolChatError, ToolSpec
from cascadasen.domain.theater.cycle import RunConfig, Simulation
from cascadasen.infrastructure.llm import ClaudeCommander, ClaudeInterpreter, llm_adapters
from cascadasen.infrastructure.llm_budget import CallBudget, LlmBudgetExceeded
from cascadasen.infrastructure.llm_tools import ConverseToolChat, tool_chat
from cascadasen.infrastructure.settings import Settings

CONVERSE = {"llm_enabled": True, "llm_provider": "bedrock-converse", "llm_model": "m"}
OPTIONS = [{"id": "backup_comms:A09"}]


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class FakeConverse:
    def __init__(self, error=None):
        self.error, self.calls = error, 0

    def converse(self, **kw):
        self.calls += 1
        if self.error and "toolConfig" in kw:
            raise self.error
        if "toolConfig" in kw and "toolChoice" not in kw["toolConfig"]:  # the assistant's call: plain text
            return {"output": {"message": {"content": [{"text": "hola"}]}}}
        return {
            "output": {
                "message": {"content": [{"toolUse": {"input": {"chosen": ["x"], "explanation": "e"}}}]}
            }
        }


class ValidationException(Exception):
    pass


def test_the_counter_caps_a_minute_and_a_day_and_refusals_are_not_counted():
    clock = Clock()
    budget = CallBudget(2, 3, clock)
    budget.spend()
    budget.spend()
    with pytest.raises(LlmBudgetExceeded):
        budget.spend()
    clock.now += 61  # the minute window moved on, the day window did not
    budget.spend()
    clock.now += 61
    with pytest.raises(LlmBudgetExceeded):  # 3 calls in the last day
        budget.spend()
    clock.now += 86400
    budget.spend()


def test_the_counter_is_built_from_the_settings():
    budget = CallBudget.from_settings(Settings(rate_llm_calls_per_minute=7, rate_llm_calls_per_day=9))
    assert (budget.per_minute, budget.per_day) == (7, 9)
    defaults = Settings()
    assert (defaults.rate_assistant_global_per_minute, defaults.rate_assistant_global_per_day) == (30, 500)
    assert (defaults.rate_assistant_concurrent_per_ip, defaults.rate_assistant_concurrent_global) == (2, 6)


def test_the_assistant_turn_is_refused_without_calling_bedrock():
    client = FakeConverse()
    chat = tool_chat(Settings(**CONVERSE, rate_llm_calls_per_minute=1), client)
    spec = ToolSpec("t", "d", {"type": "object"})
    chat.turn("s", [{"role": "user", "text": "hola"}], [spec])
    with pytest.raises(ToolChatError, match="límite de uso"):
        chat.turn("s", [{"role": "user", "text": "hola"}], [spec])
    assert client.calls == 1


def test_a_turn_without_a_budget_is_not_capped():
    client = FakeConverse()
    chat = ConverseToolChat("m", client)
    for _ in range(3):
        chat.turn("s", [{"role": "user", "text": "hola"}], [])
    assert client.calls == 3


def test_the_commander_falls_back_to_the_rules_when_refused():
    client = FakeConverse()
    commander = ClaudeCommander(Settings(**CONVERSE), client=client, budget=CallBudget(1, 10))
    assert commander.choose({}, OPTIONS, 1) == {"chosen": ["x"], "explanation": "e"}
    assert commander.choose({}, OPTIONS, 1) is None  # None is "use the rules"
    assert client.calls == 1


def test_the_second_call_of_the_prompt_fallback_is_counted_too():
    client = FakeConverse(error=ValidationException("toolChoice not supported"))
    commander = ClaudeCommander(Settings(**CONVERSE), client=client, budget=CallBudget(1, 10))
    assert commander.choose({}, OPTIONS, 1) is None
    assert client.calls == 1  # the forced call went out, the retry was refused


def test_the_interpreter_keeps_the_template_when_refused(toy_world):
    sim = Simulation(toy_world, RunConfig(template="open_field", seed=2, horizon=4))
    sim.run_to_end()
    client = FakeConverse()
    interpreter = ClaudeInterpreter(Settings(**CONVERSE), client=client, budget=CallBudget(0, 0))
    out = interpreter.after_action(sim.report(), sim.snapshots)
    assert out["interpreter"] == "template" and out["summary"] and client.calls == 0


def test_the_adapters_share_one_budget(monkeypatch):
    # boto3 needs a region to build the client; CI has none configured.
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    interpreter, advisor = llm_adapters(Settings(**CONVERSE), CallBudget(1, 10))
    assert interpreter.budget is advisor.budget
    interpreter, advisor = llm_adapters(Settings(**CONVERSE))
    assert interpreter.budget is advisor.budget
