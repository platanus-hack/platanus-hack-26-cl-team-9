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


def test_a_message_runs_tools_through_the_real_routes(make_app):
    model = ScriptedModel(
        calls(("start_session", {}), ("describe_network", {}), ("start_run", {"horizon": 4})),
        AssistantTurn("Abrí la corrida."),
    )
    client = TestClient(make_app(model))
    out = client.post(CHAT, json={"message": "abre una corrida"}).json()
    assert out["reply"] == "Abrí la corrida." and out["steps"] == 2 and out["truncated"] is None
    assert [t["name"] for t in out["tool_calls"]] == ["start_session", "describe_network", "start_run"]
    assert all(t["ok"] for t in out["tool_calls"])
    sid, rid = out["session_id"], out["run_id"]
    doc = client.get(f"/api/v1/sessions/{sid}").json()
    assert rid in doc["runs"] and doc["last_op"]["by"] == "asistente"
    assert "Sub50 simulates" in model.systems[0]  # the shared guardrails are in the prompt
    assert "places" in model.systems[0]  # and how to put a point on the map


def test_a_point_lands_at_the_substation_that_serves_the_place(make_app):
    """prepare_scenario resolves "Iquique" and "Antofagasta" on the real 188-bus grid (docs/stress.md)."""
    changes = [
        {"target": "demand", "places": ["Antofagasta"], "add": 120},
        {"target": "generation", "places": ["Iquique"], "tech": ["solar"], "add": 80},
    ]
    model = ScriptedModel(calls(("prepare_scenario", {"changes": changes})), AssistantTurn("Listo."))
    msg = "datacenter de 120 MW en Antofagasta y una solar de 80 MW en Iquique"
    out = TestClient(make_app(model)).post(CHAT, json={"message": msg}).json()
    tool = out["tool_calls"][0]
    assert tool["ok"], tool["result"]
    dc, solar = tool["result"]["prepared"]["changes"]
    assert dc["places"][0]["bus_name"] == "S/E ANTOFAGASTA" and dc["load_delta_mw"] == 120.0
    assert solar["places"][0]["bus_name"] == "S/E CONDORES" and solar["new_plant"] is True
    assert solar["gen_delta_mw"] == 80.0 and "warning" not in solar
    assert tool["result"]["scenario"]["changes"] == changes  # what the web loads on the map


def test_the_conversation_continues_and_can_be_read_and_deleted(make_app):
    model = ScriptedModel(calls(("describe_network", {})), AssistantTurn("listo"), AssistantTurn("sigo"))
    client = TestClient(make_app(model))
    first = client.post(CHAT, json={"message": "crea una sesión"}).json()
    cid, sid = first["conversation_id"], first["session_id"]
    second = client.post(CHAT, json={"message": "sigue", "conversation_id": cid}).json()
    assert second["session_id"] == sid and second["reply"] == "sigo"
    read = client.get(f"/api/v1/assistant/conversations/{cid}").json()
    assert [t["role"] for t in read["turns"]] == ["user", "assistant", "user", "assistant"]
    assert read["tool_calls"][0]["name"] == "describe_network"
    assert client.delete(f"/api/v1/assistant/conversations/{cid}").status_code == 204
    assert client.get(f"/api/v1/assistant/conversations/{cid}").status_code == 404
    assert client.get(f"/api/v1/sessions/{sid}").status_code == 200  # the session stays


def test_tool_errors_reach_the_model_not_the_client(make_app):
    model = ScriptedModel(
        calls(
            ("start_session", {}),
            ("start_incident_run", {"scenario": "no-existe"}),
            ("cut_lines", {"lines": ["R1"]}),
        ),
        AssistantTurn("ese incidente no existe"),
    )
    out = TestClient(make_app(model)).post(CHAT, json={"message": "corre el incidente no-existe"}).json()
    assert [t["ok"] for t in out["tool_calls"]] == [True, False, False]
    assert "422" in out["tool_calls"][1]["result"]["error"]
    # session cuts are not the assistant's: the map draws only prepare_scenario's grid
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
    event = ("inject_event", {"type": "C3_transmission_opening", "target": "T2-T3"})
    model = ScriptedModel(
        calls(("start_session", {}), ("start_run", {}), event, event, event), AssistantTurn("ok")
    )
    app = make_app(model, rate_writes_per_minute=2)
    out = TestClient(app).post(CHAT, json={"message": "abre T2-T3 tres veces"}).json()
    assert [t["ok"] for t in out["tool_calls"][1:]] == [True, True, False, False]
    assert "espera" in out["tool_calls"][3]["result"]["error"]


def test_a_tool_that_needs_a_session_opens_it_without_the_user(make_app):
    model = ScriptedModel(calls(("describe_network", {})), AssistantTurn("Esta es la red."))
    client = TestClient(make_app(model))
    out = client.post(CHAT, json={"message": "describe la red"}).json()
    assert out["tool_calls"][0]["ok"] is True and "automáticamente" in out["tool_calls"][0]["result"]["nota"]
    sid = out["session_id"]
    assert sid and client.get(f"/api/v1/sessions/{sid}").status_code == 200


def test_an_event_before_start_run_opens_a_run_and_step_reports_what_happened(make_app, monkeypatch):
    # The run opened by inject_event has no seed, so it draws a fresh one and a background event (E1, E2...) can
    # land in the second step on about 1 run in 25. Pin the seed: the test is about the tool loop, not the dice.
    monkeypatch.setattr("cascadasen.domain.theater.cycle.new_seed", lambda: 7)
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
        AssistantTurn("Abro la corrida.", (ToolCall("c1", "start_run", {"horizon": 4}),)),
        calls(("inject_event", {"type": "C3_transmission_opening", "target": "T2-T3"})),
        AssistantTurn("Listo."),
    )
    client = TestClient(make_app(model))
    r = client.post(STREAM, json={"message": "abre una corrida y el corredor T2-T3"})
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
    run_result, event_result = events[3][1], events[5][1]
    assert run_result["name"] == "start_run" and run_result["ok"] and run_result["session_id"]
    assert run_result["run_id"] and event_result["result"]["accepted"]
    done = events[-1][1]
    assert done["reply"] == "Listo." and done["session_id"] == run_result["session_id"]
    # the client fetches the full state the event points to
    run = client.get(f"/api/v1/sessions/{done['session_id']}/runs/{done['run_id']}").json()
    assert run["run"]["run_id"] == done["run_id"]
    # the conversation is the same one /chat would have stored
    read = client.get(f"/api/v1/assistant/conversations/{done['conversation_id']}").json()
    assert [t["name"] for t in read["tool_calls"]] == ["start_run", "inject_event"]


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


def test_grid_context_names_the_loaded_grid():
    from cascadasen.api.assistant_routes import GridIn, grid_context

    text = grid_context(GridIn(point="feb2025-1500", open_lines=["R239"], out_buses=["B043"]))
    assert "feb2025-1500" in text and "R239" in text and "B043" in text
    assert grid_context(None) == ""
