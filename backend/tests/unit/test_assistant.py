"""The assistant's tool-use loop with a scripted model and a fake toolbox (docs/assistant.md)."""

import pytest

from cascadasen.application.assistant import (
    Assistant,
    AssistantInputError,
    ConversationConflictError,
    ConversationNotFoundError,
    trim_history,
    trim_result,
)
from cascadasen.domain.ports import AssistantTurn, ToolCall, ToolChatError, ToolSpec
from cascadasen.infrastructure.document_store import MemoryDocumentStore
from cascadasen.mcp.client import Sub50Client, ToolError
from cascadasen.mcp.state import McpState
from cascadasen.mcp.toolbox import SessionTools
from cascadasen.mcp.tools import Sub50Tools

SID = "A" * 22


class ScriptedModel:
    """Answers with the next scripted turn and records what it was sent."""

    def __init__(self, *turns):
        self.turns, self.seen = list(turns), []

    def turn(self, system, messages, tools):
        self.seen.append([dict(m) for m in messages])
        nxt = self.turns.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


class FakeBox:
    def __init__(self, fail=False):
        self.calls, self.fail, self.ctx = [], fail, {"session_id": None, "run_id": None}

    def specs(self):
        return [ToolSpec("start_session", "x", {"type": "object"})]

    def run(self, call):
        self.calls.append(call)
        if call.name == "start_session":
            self.ctx["session_id"] = SID
        return (False, {"error": "mal"}) if self.fail else (True, {"ok": call.name})

    def context(self):
        return dict(self.ctx)


def call(name="start_session", id="c1", **arguments):
    return ToolCall(id, name, arguments)


def make(model, **kw):
    return Assistant(model, MemoryDocumentStore(), "sistema", notice="aviso", **kw)


def test_plain_answer_without_tools():
    a = make(ScriptedModel(AssistantTurn("hola")))
    out = a.chat("hola", None, None, lambda s, r: FakeBox())
    assert out["reply"] == "hola" and out["tool_calls"] == [] and out["truncated"] is None
    assert out["steps"] == 1 and out["notice"] == "aviso" and len(out["conversation_id"]) == 22


def test_tool_calls_run_and_the_session_is_remembered_across_messages():
    model = ScriptedModel(AssistantTurn("", (call(),)), AssistantTurn("listo"), AssistantTurn("otra vez"))
    a, boxes = make(model), []

    def box(sid, rid):
        boxes.append((sid, rid))
        return FakeBox()

    first = a.chat("crea una sesión", None, None, box)
    assert first["reply"] == "listo" and first["steps"] == 2
    assert first["tool_calls"] == [
        {"name": "start_session", "arguments": {}, "ok": True, "result": {"ok": "start_session"}}
    ]
    assert first["session_id"] == SID
    second = a.chat("sigue", first["conversation_id"], None, box)
    assert boxes == [(None, None), (SID, None)] and second["reply"] == "otra vez"
    assert second["tool_calls"] == []  # the trace is of this message only
    assert len(model.seen[2]) == 5  # user, assistant+call, tool, assistant, user: the history came back


def test_a_failed_tool_goes_back_to_the_model_and_the_loop_continues():
    model = ScriptedModel(AssistantTurn("", (call(),)), AssistantTurn("no se pudo"))
    out = make(model).chat("x", None, None, lambda s, r: FakeBox(fail=True))
    assert out["tool_calls"][0]["ok"] is False and out["reply"] == "no se pudo"
    assert model.seen[1][-1] == {
        "role": "tool",
        "tool_call_id": "c1",
        "ok": False,
        "result": {"error": "mal"},
    }


def test_the_step_cap_ends_the_message_and_keeps_roles_alternating():
    model = ScriptedModel(*[AssistantTurn("", (call(id=f"c{i}"),)) for i in range(3)])
    a = make(model, max_steps=3)
    out = a.chat("x", None, None, lambda s, r: FakeBox())
    assert out["truncated"] == "steps" and "continúa" in out["reply"] and out["steps"] == 3
    doc, _ = a.load(out["conversation_id"])
    assert doc["messages"][-1]["role"] == "assistant"


def test_the_deadline_stops_before_the_next_model_call():
    now = iter([0.0, 0.0, 0.0, 1.0, 30.0, 30.0, 30.0])
    model = ScriptedModel(AssistantTurn("", (call(),)))
    out = make(model, deadline_s=25, clock=lambda: next(now)).chat("x", None, None, lambda s, r: FakeBox())
    assert out["truncated"] == "deadline" and out["steps"] == 1


def test_a_model_failure_keeps_the_turn_and_raises():
    a = make(ScriptedModel(ToolChatError("no disponible"), AssistantTurn("ya")))
    with pytest.raises(ToolChatError):
        a.chat("primero", None, None, lambda s, r: FakeBox())
    cid = next(k for k in a.store._docs).removeprefix("assistant/").removesuffix(".json")
    doc, _ = a.load(cid)
    assert [m["role"] for m in doc["messages"]] == ["user", "assistant"]
    assert a.chat("de nuevo", cid, None, lambda s, r: FakeBox())["reply"] == "ya"


def test_unknown_conversation_bad_session_id_and_delete():
    a = make(ScriptedModel(AssistantTurn("hola")))
    with pytest.raises(ConversationNotFoundError):
        a.chat("x", "nope", None, lambda s, r: FakeBox())
    with pytest.raises(AssistantInputError):
        a.chat("x", None, "corto", lambda s, r: FakeBox())
    cid = a.chat("x", None, SID, lambda s, r: FakeBox())["conversation_id"]
    a.delete(cid)
    with pytest.raises(ConversationNotFoundError):
        a.load(cid)


def test_a_concurrent_message_loses_with_a_conflict():
    a = make(ScriptedModel(AssistantTurn("uno"), AssistantTurn("dos"), AssistantTurn("tres")))
    cid = a.chat("x", None, None, lambda s, r: FakeBox())["conversation_id"]

    def racing(sid, rid):
        a.store.put(f"assistant/{cid}.json", {**a.load(cid)[0], "updated_at": "otro"})  # another writer
        return FakeBox()

    with pytest.raises(ConversationConflictError):
        a.chat("y", cid, None, racing)


def test_history_is_trimmed_at_a_user_turn_and_big_results_are_cut():
    msgs = [
        {"role": "user", "text": "1"},
        {"role": "assistant", "text": "", "tool_calls": [{"id": "a", "name": "n", "arguments": {}}]},
        {"role": "tool", "tool_call_id": "a", "ok": True, "result": {}},
        {"role": "assistant", "text": "r"},
        {"role": "user", "text": "2"},
        {"role": "assistant", "text": "r2"},
    ]
    assert [m["role"] for m in trim_history(msgs, 4)] == ["user", "assistant"]  # starts at "2"
    assert trim_history(msgs, 10) == msgs
    cut = trim_result({"x": "y" * 20000})
    assert cut["truncated"] is True and len(cut["preview"]) == 8000


def test_session_tools_reject_unknown_and_excluded_tools_and_cap_step_cycles():
    seen = {}

    class Tools(Sub50Tools):
        def step(self, cycles: int = 1):
            seen["cycles"] = cycles
            return {"cycles": cycles}

        def run_status(self):
            raise ToolError("sin corrida")

    box = SessionTools(Tools(Sub50Client(base_url="http://x"), McpState(SID)))
    assert box.run(call("end_session")) == (False, {"error": "Herramienta desconocida: end_session"})
    assert box.run(call("nada"))[0] is False
    assert box.run(call("step", cycles=500)) == (True, {"cycles": 24}) and seen["cycles"] == 24
    assert box.run(call("run_status")) == (False, {"error": "sin corrida"})
    assert box.run(call("step", otra=1))[1]["error"].startswith("Argumentos inválidos")
    names = {s.name for s in box.specs()}
    assert "end_session" not in names


def test_the_assistant_edits_only_through_the_grid_the_map_draws():
    """The web draws only prepare_scenario's grid (#101): session edits and cuts never reached the map."""
    names = {s.name for s in SessionTools(Sub50Tools(Sub50Client(base_url="http://x"))).specs()}
    hidden = {"add_datacenter", "add_generator", "add_line", "add_bus", "edit_element", "remove_element"}
    assert not names & (hidden | {"cut_lines", "repair_lines", "reset_network", "get_grid_state"})
    assert {"prepare_scenario", "describe_network", "start_run", "step", "start_incident_run"} <= names


def test_the_first_tool_that_needs_a_session_opens_one_and_says_so():
    started = []

    class Tools(Sub50Tools):
        def start_session(self, point: str | None = None, label: str | None = None):
            started.append(1)
            self.state.session_id = SID
            return {"session_id": SID}

        def describe_network(self, focus: str | None = None):
            return {"areas": []}

        def list_options(self):
            return {"templates": []}

    box = SessionTools(Tools(Sub50Client(base_url="http://x")))
    assert box.run(call("list_options")) == (True, {"templates": []})  # needs no session
    assert not started
    ok, first = box.run(call("describe_network"))
    assert ok and "automáticamente" in first["nota"] and started == [1]
    ok, second = box.run(call("describe_network"))
    assert ok and "nota" not in second and started == [1]
    assert box.context()["session_id"] == SID


def test_an_announced_but_unrun_action_gets_one_hidden_nudge():
    model = ScriptedModel(
        AssistantTurn("La línea es R007. La cortaré junto con las anteriores."),
        AssistantTurn("", (call(),)),
        AssistantTurn("Listo, la corté."),
    )
    a = make(model)
    out = a.chat("corta la línea entre A y B", None, None, lambda s, r: FakeBox())
    assert out["reply"] == "Listo, la corté." and [t["name"] for t in out["tool_calls"]] == ["start_session"]
    nudge = model.seen[1][-1]
    assert nudge["role"] == "user" and nudge["hidden"] is True
    turns = a.load(out["conversation_id"])[0]
    from cascadasen.application.assistant import view

    assert all("interno" not in t["text"] for t in view(turns)["turns"])  # the user never sees it


def test_no_nudge_for_questions_past_tense_or_twice():
    from cascadasen.application.assistant import announces

    assert announces("Voy a cortar R007.") and announces("Cortaré R007 ahora.")
    assert not announces("¿Quieres que la corte?") and not announces("Reparé todas las líneas.")
    assert not announces("Comparé las dos políticas.")
    model = ScriptedModel(AssistantTurn("Haré el corte."), AssistantTurn("Haré el corte."))
    out = make(model).chat("x", None, None, lambda s, r: FakeBox())
    assert out["reply"] == "Haré el corte." and out["steps"] == 2  # only one nudge


def test_offers_waiting_for_the_user_get_no_nudge():
    from cascadasen.application.assistant import announces

    assert not announces("Dime tu acción y la ejecutaré inmediatamente.")
    assert not announces("Si quieres, cortaré otra línea.")
    assert announces("La línea es R007. La cortaré junto con las anteriores.")


def test_a_call_that_would_end_past_the_deadline_is_not_started():
    # start 0; step 1: check 0, call 0 -> 12 (mean 12); step 2: check 14 + 12 > 25 -> stop
    now = iter([0.0, 0.0, 0.0, 12.0, 14.0])
    model = ScriptedModel(AssistantTurn("", (call(),)), AssistantTurn("no debería llegar"))
    out = make(model, deadline_s=25, clock=lambda: next(now)).chat("x", None, None, lambda s, r: FakeBox())
    assert out["truncated"] == "deadline" and out["steps"] == 1 and len(model.turns) == 1


def test_steps_are_emitted_as_they_happen():
    events = []
    model = ScriptedModel(AssistantTurn("Creo la sesión.", (call(),)), AssistantTurn("listo"))
    out = make(model).chat(
        "x", None, None, lambda s, r: FakeBox(), on_event=lambda k, d: events.append((k, d))
    )
    assert [k for k, _ in events] == ["start", "assistant_text", "tool_call", "tool_result"]
    start, text, tool_call, tool_result = (d for _, d in events)
    assert start["conversation_id"] == out["conversation_id"] and start["session_id"] is None
    assert text == {"step": 1, "text": "Creo la sesión."}
    assert tool_call == {"step": 1, "id": "c1", "name": "start_session", "arguments": {}}
    assert tool_result["ok"] is True and tool_result["result"] == {"ok": "start_session"}
    assert tool_result["session_id"] == SID  # where the client fetches the new state


def test_a_failing_event_callback_does_not_stop_the_conversation():
    def broken(kind, data):
        raise BrokenPipeError

    model = ScriptedModel(AssistantTurn("", (call(),)), AssistantTurn("listo"))
    out = make(model).chat("x", None, None, lambda s, r: FakeBox(), on_event=broken)
    assert out["reply"] == "listo" and out["tool_calls"][0]["ok"] is True


def test_a_longer_deadline_can_be_given_per_message():
    now = iter([0.0, 0.0, 0.0, 30.0, 31.0, 31.0, 40.0])
    model = ScriptedModel(AssistantTurn("", (call(),)), AssistantTurn("listo"))
    a = make(model, deadline_s=25, clock=lambda: next(now))
    out = a.chat("x", None, None, lambda s, r: FakeBox(), deadline_s=90)
    assert out["reply"] == "listo" and out["truncated"] is None


def test_the_model_sizes_the_megawatts_when_the_user_gave_none():
    """The user asks for help and is not technical: the toolbox does not make the model ask for MW (#125)."""

    class Tools(Sub50Tools):
        def add_generator(self, bus: str, mw: float, tech: str, name: str | None = None):
            return {"mw": mw}

        def prepare_scenario(
            self,
            changes: list[dict] | None = None,
            open_lines: list[str] | None = None,
            out_buses: list[str] | None = None,
            point: str | None = None,
        ):
            return {"changes": changes}

    box = SessionTools(Tools(Sub50Client(base_url="http://x"), McpState(SID)), frozenset())
    assert box.run(call("add_generator", bus="Vallenar", mw=120, tech="solar")) == (True, {"mw": 120})
    change = {"target": "generation", "places": ["Calama"], "add": 300}
    assert box.run(call("prepare_scenario", changes=[change]))[0]


def test_a_first_session_at_the_default_point_waits_until_a_tool_needs_it():
    """The model opened a session before every map change; prepare_scenario never uses one."""
    opened = []

    class Tools(Sub50Tools):
        def start_session(self, point: str | None = None, label: str | None = None):
            opened.append(point)
            self.state.session_id = SID
            return {"session_id": SID, "point": point}

    box = SessionTools(Tools(Sub50Client(base_url="http://x")))
    ok, out = box.run(call("start_session"))
    assert ok and out["deferred"] and not opened
    assert box.run(call("start_session", point="nov2026-1300"))[1]["deferred"] and not opened
    ok, out = box.run(call("start_session", point="feb2025-1500"))  # an incident's own point: open it now
    assert ok and out["session_id"] == SID and opened == ["feb2025-1500"]


def test_the_system_prompt_only_names_tools_the_assistant_is_offered():
    import re

    from cascadasen.api.assistant_routes import SYSTEM
    from cascadasen.mcp.toolbox import EXCLUDED
    from cascadasen.mcp.tools import TOOLS

    named = {t for t in TOOLS if re.search(rf"\b{t}\b", SYSTEM)}
    assert {"describe_network", "prepare_scenario"} <= named
    assert not named & EXCLUDED, named & EXCLUDED
