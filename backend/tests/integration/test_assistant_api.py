"""The assistant over HTTP on the toy world: a scripted model drives the real session routes."""

import pytest
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.api.assistant_routes import SYSTEM
from cascadasen.application.assistant import Assistant
from cascadasen.application.grid_queries import GridQueryService
from cascadasen.application.run_experiment import RunCache
from cascadasen.application.sessions import SessionService
from cascadasen.application.simulation_service import SimulationService
from cascadasen.domain.ports import AssistantTurn, ToolCall, ToolChatError
from cascadasen.domain.simulation.grid import Physics
from cascadasen.infrastructure.document_store import MemoryDocumentStore
from cascadasen.infrastructure.settings import Settings

CHAT = "/api/v1/assistant/chat"


class ScriptedModel:
    def __init__(self, *turns):
        self.turns, self.systems = list(turns), []

    def turn(self, system, messages, tools):
        self.systems.append(system)
        nxt = self.turns.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def calls(*items):
    return AssistantTurn("", tuple(ToolCall(f"c{i}", n, a) for i, (n, a) in enumerate(items)))


@pytest.fixture(scope="module")
def physics():
    return Physics.load()


@pytest.fixture
def make_app(toy_snapshot, toy_network, toy_world, toy_spec, physics):
    def build(model=None, **settings):
        store, cache = MemoryDocumentStore(), RunCache()
        app = create_app(
            service=GridQueryService(toy_snapshot),
            simulation=SimulationService(toy_network, physics, world=toy_world, store=store, run_cache=cache),
            sessions=SessionService(toy_world, physics, store, cache, spec=toy_spec),
            settings=Settings(rate_create_per_hour=50, llm_enabled=False, **settings),
        )
        if model is not None:
            app.state.assistant = Assistant(model, store, SYSTEM, notice="aviso")
        return app

    return build


def test_a_message_edits_and_cuts_through_the_real_routes(make_app):
    model = ScriptedModel(
        calls(
            ("start_session", {}),
            ("add_datacenter", {"bus": "B002", "mw": 100, "name": "DC Toy"}),
            ("cut_lines", {"lines": ["R1"]}),
        ),
        AssistantTurn("Agregué el datacenter y corté R1."),
    )
    client = TestClient(make_app(model))
    out = client.post(CHAT, json={"message": "agrega un datacenter de 100 MW y corta R1"}).json()
    assert out["reply"].startswith("Agregué") and out["steps"] == 2 and out["truncated"] is None
    assert [t["name"] for t in out["tool_calls"]] == ["start_session", "add_datacenter", "cut_lines"]
    assert all(t["ok"] for t in out["tool_calls"])
    sid = out["session_id"]
    doc = client.get(f"/api/v1/sessions/{sid}").json()
    assert doc["open_lines"] == ["R1"] and doc["last_op"]["by"] == "asistente"
    assert client.get(f"/api/v1/sessions/{sid}/network").json()["loads"][0]["name"] == "DC Toy"
    assert "Sub50 simulates" in model.systems[0]  # the shared guardrails are in the prompt


def test_the_conversation_continues_and_can_be_read_and_deleted(make_app):
    model = ScriptedModel(calls(("start_session", {})), AssistantTurn("listo"), AssistantTurn("sigo"))
    client = TestClient(make_app(model))
    first = client.post(CHAT, json={"message": "crea una sesión"}).json()
    cid, sid = first["conversation_id"], first["session_id"]
    second = client.post(CHAT, json={"message": "sigue", "conversation_id": cid}).json()
    assert second["session_id"] == sid and second["reply"] == "sigo"
    read = client.get(f"/api/v1/assistant/conversations/{cid}").json()
    assert [t["role"] for t in read["turns"]] == ["user", "assistant", "user", "assistant"]
    assert read["tool_calls"][0]["name"] == "start_session"
    assert client.delete(f"/api/v1/assistant/conversations/{cid}").status_code == 204
    assert client.get(f"/api/v1/assistant/conversations/{cid}").status_code == 404
    assert client.get(f"/api/v1/sessions/{sid}").status_code == 200  # the session stays


def test_tool_errors_reach_the_model_not_the_client(make_app):
    model = ScriptedModel(
        calls(("start_session", {}), ("cut_lines", {"lines": ["R99"]}), ("end_session", {})),
        AssistantTurn("esa línea no existe"),
    )
    out = TestClient(make_app(model)).post(CHAT, json={"message": "corta R99"}).json()
    assert [t["ok"] for t in out["tool_calls"]] == [True, False, False]
    assert "404" in out["tool_calls"][1]["result"]["error"]
    assert out["tool_calls"][2]["result"]["error"].startswith("Herramienta desconocida")


def test_unavailable_without_the_llm_and_input_errors(make_app):
    client = TestClient(make_app())
    assert client.post(CHAT, json={"message": "hola"}).status_code == 503
    client = TestClient(make_app(ScriptedModel()))
    assert client.post(CHAT, json={"message": ""}).status_code == 422
    assert client.post(CHAT, json={"message": "x" * 2001}).status_code == 422
    assert client.post(CHAT, json={"message": "x", "conversation_id": "corto"}).status_code == 422
    assert client.post(CHAT, json={"message": "x", "conversation_id": "A" * 22}).status_code == 404
    big = client.post(CHAT, content=b"x" * 70000, headers={"content-type": "application/json"})
    assert big.status_code == 413


def test_a_model_failure_is_a_502_without_internal_detail(make_app):
    client = TestClient(make_app(ScriptedModel(ToolChatError("El modelo no está disponible"))))
    out = client.post(CHAT, json={"message": "hola"})
    assert out.status_code == 502 and "no está disponible" in out.json()["detail"]


def test_the_chat_is_rate_limited_per_client_ip(make_app):
    model = ScriptedModel(*[AssistantTurn("ok") for _ in range(20)])
    client = TestClient(make_app(model, rate_assistant_per_minute=2))
    assert [client.post(CHAT, json={"message": "x"}).status_code for _ in range(3)] == [200, 200, 429]


def test_session_write_limits_count_against_the_caller_not_a_shared_loopback(make_app):
    adds = [("add_datacenter", {"bus": "B002", "mw": 1, "name": f"DC{i}"}) for i in range(4)]
    model = ScriptedModel(calls(("start_session", {}), *adds), AssistantTurn("ok"))
    app = make_app(model, rate_writes_per_minute=2)
    out = TestClient(app).post(CHAT, json={"message": "agrega cuatro de 1 MW"}).json()
    assert [t["ok"] for t in out["tool_calls"][1:]] == [True, True, False, False]
    assert "espera" in out["tool_calls"][3]["result"]["error"]


def test_a_tool_that_needs_a_session_opens_it_without_the_user(make_app):
    model = ScriptedModel(
        calls(("add_datacenter", {"bus": "B002", "mw": 100, "name": "DC Toy"})), AssistantTurn("Agregado.")
    )
    client = TestClient(make_app(model))
    out = client.post(CHAT, json={"message": "agrega un datacenter de 100 MW"}).json()
    assert out["tool_calls"][0]["ok"] is True and "automáticamente" in out["tool_calls"][0]["result"]["nota"]
    sid = out["session_id"]
    assert sid and client.get(f"/api/v1/sessions/{sid}/network").json()["loads"][0]["name"] == "DC Toy"


def test_an_event_before_start_run_opens_a_run_and_step_reports_what_happened(make_app):
    model = ScriptedModel(
        calls(
            ("inject_event", {"type": "C3_transmission_opening", "target": "T2-T3"}), ("step", {"cycles": 1})
        ),
        calls(("step", {"cycles": 1})),
        AssistantTurn("listo"),
    )
    out = TestClient(make_app(model)).post(CHAT, json={"message": "abre T2-T3 y avanza"}).json()
    inject, first, second = out["tool_calls"]
    assert inject["ok"] and "corrida" in inject["result"]["nota"] and out["run_id"]
    assert [e["type"] for e in first["result"]["events_applied"]] == ["C3_transmission_opening"]
    assert "warning" not in first["result"]
    assert second["result"]["events_applied"] == [] and "No se aplicó" in second["result"]["warning"]


STREAM = "/api/v1/assistant/chat/stream"


def parse_sse(text):
    """[(event, data)] from a text/event-stream body; comments (pings) are skipped."""
    import json

    out = []
    for block in text.strip().split("\n\n"):
        lines = [ln for ln in block.splitlines() if not ln.startswith(":")]
        if not lines:
            continue
        kind = next(ln[7:] for ln in lines if ln.startswith("event: "))
        data = json.loads(next(ln[6:] for ln in lines if ln.startswith("data: ")))
        out.append((kind, data))
    return out


def test_the_stream_sends_each_step_then_done(make_app):
    model = ScriptedModel(
        AssistantTurn(
            "Agrego el datacenter.", (ToolCall("c1", "add_datacenter", {"bus": "B002", "mw": 100}),)
        ),
        calls(("cut_lines", {"lines": ["R1"]})),
        AssistantTurn("Listo."),
    )
    client = TestClient(make_app(model))
    r = client.post(STREAM, json={"message": "agrega un datacenter de 100 MW y corta R1"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    assert [k for k, _ in events] == [
        "start",
        "assistant_text",
        "tool_call",
        "tool_result",
        "tool_call",
        "tool_result",
        "done",
    ]
    by = dict(events[:1])
    assert by["start"]["session_id"] is None
    dc_result, cut_result = events[3][1], events[5][1]
    assert dc_result["name"] == "add_datacenter" and dc_result["ok"] and dc_result["session_id"]
    assert cut_result["result"]["open_lines"] == ["R1"]
    done = events[-1][1]
    assert done["reply"] == "Listo." and done["session_id"] == dc_result["session_id"]
    # the client fetches the full state the event points to
    state = client.get(f"/api/v1/sessions/{done['session_id']}/state").json()
    assert state["open_lines"] == ["R1"] and state["timeline"]["frames"]
    # the conversation is the same one /chat would have stored
    read = client.get(f"/api/v1/assistant/conversations/{done['conversation_id']}").json()
    assert [t["name"] for t in read["tool_calls"]] == ["add_datacenter", "cut_lines"]


def test_stream_errors_before_and_after_it_starts(make_app):
    client = TestClient(make_app())
    assert client.post(STREAM, json={"message": "hola"}).status_code == 503
    client = TestClient(make_app(ScriptedModel(ToolChatError("El modelo no está disponible"))))
    assert client.post(STREAM, json={"message": ""}).status_code == 422
    assert client.post(STREAM, json={"message": "x", "conversation_id": "A" * 22}).status_code == 404
    events = parse_sse(client.post(STREAM, json={"message": "hola"}).text)
    assert [k for k, _ in events] == ["start", "error"]
    assert events[1][1] == {"status": 502, "detail": "El modelo no está disponible"}


def test_the_stream_shares_the_chat_rate_limit(make_app):
    model = ScriptedModel(*[AssistantTurn("ok") for _ in range(5)])
    client = TestClient(make_app(model, rate_assistant_per_minute=2))
    codes = [
        client.post(STREAM, json={"message": "x"}).status_code,
        client.post(CHAT, json={"message": "x"}).status_code,
    ]
    assert codes == [200, 200] and client.post(STREAM, json={"message": "x"}).status_code == 429


def test_the_stream_pings_while_the_model_thinks(make_app):
    import time as _time

    class SlowModel(ScriptedModel):
        def turn(self, system, messages, tools):
            _time.sleep(0.3)
            return super().turn(system, messages, tools)

    client = TestClient(make_app(SlowModel(AssistantTurn("ok")), assistant_stream_ping_s=0.05))
    body = client.post(STREAM, json={"message": "x"}).text
    assert ": ping" in body and parse_sse(body)[-1][0] == "done"
