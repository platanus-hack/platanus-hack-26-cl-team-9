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
    out = client.post(CHAT, json={"message": "agrega un datacenter y corta R1"}).json()
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
    out = TestClient(app).post(CHAT, json={"message": "agrega cuatro"}).json()
    assert [t["ok"] for t in out["tool_calls"][1:]] == [True, True, False, False]
    assert "espera" in out["tool_calls"][3]["result"]["error"]
