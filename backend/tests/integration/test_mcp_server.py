"""The MCP server driving the real FastAPI app on the toy world through its tools (docs/mcp.md)."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("mcp")

from pathlib import Path

from cascadasen.api.app import create_app
from cascadasen.application.grid_queries import GridQueryService
from cascadasen.application.run_experiment import RunCache
from cascadasen.application.sessions import SessionService
from cascadasen.application.simulation_service import SimulationService
from cascadasen.domain.simulation.grid import Physics
from cascadasen.infrastructure.document_store import MemoryDocumentStore
from cascadasen.infrastructure.settings import Settings
from cascadasen.mcp.client import Sub50Client, ToolError
from cascadasen.mcp.server import INSTRUCTIONS, build_server
from cascadasen.mcp.state import McpState
from cascadasen.mcp.tools import OPERATIONS, TOOLS, Sub50Tools

SPEC = Path(__file__).resolve().parents[3] / "docs" / "openapi" / "agents.openapi.json"


@pytest.fixture(scope="module")
def physics():
    return Physics.load()


@pytest.fixture
def http(toy_snapshot, toy_network, toy_world, toy_spec, physics):
    store, cache = MemoryDocumentStore(), RunCache()
    app = create_app(
        service=GridQueryService(toy_snapshot),
        simulation=SimulationService(toy_network, physics, world=toy_world, store=store, run_cache=cache),
        sessions=SessionService(toy_world, physics, store, cache, spec=toy_spec),
        settings=Settings(rate_create_per_hour=50),
    )
    return TestClient(app)


@pytest.fixture
def tools(http):
    return Sub50Tools(Sub50Client(http=http, agent="mcp-test"), McpState())


def test_edit_cut_and_run_in_plain_steps(tools, http):
    started = tools.start_session(label="Equipo")
    sid = started["session_id"]
    assert started["share_path"] == f"/?sesion={sid}"

    dc = tools.add_datacenter(bus="B002", mw=100, name="DC Toy")
    assert dc["id"] == "D001" and dc["redispatch"][0]["is_assumption"] is True and dc["notice"]
    assert http.get(f"/api/v1/sessions/{sid}").json()["last_op"]["by"] == "mcp-test"

    cut = tools.cut_lines(["R1"])
    assert cut["open_lines"] == ["R1"] and cut["notice"] and "frames" not in cut
    assert tools.get_grid_state()["open_lines"] == ["R1"]
    assert tools.repair_lines()["open_lines"] == []

    run = tools.start_run(template="open_field", seed=3, horizon=8)
    assert run["run_id"] == tools.state.run_id
    ev = tools.inject_event("C3_transmission_opening", "T2-T3")
    assert ev["accepted"] is True
    stepped = tools.step(2)
    assert stepped["run"]["cycle"] == 2 and len(stepped["cycles"]) == 2
    assert tools.submit_action("restore_element", "T2-T3", "operations")["accepted"] is True
    assert tools.run_report()["notice"]
    assert tools.after_action()["summary"]
    assert tools.replay("A")["replay_of"] == run["run_id"]

    tools.edit_element("D001", {"mw": 50})
    assert tools.describe_network()["added_loads"][0]["mw"] == 50
    tools.remove_element("D001")
    assert tools.describe_network()["added_loads"] == []
    assert tools.reset_network()["reset"] is True


def test_invalid_input_comes_back_as_a_readable_error(tools):
    tools.start_session()
    with pytest.raises(ToolError, match="API respondió 404"):
        tools.cut_lines(["R99"])
    with pytest.raises(ToolError, match="No pude elegir"):
        tools.add_datacenter(bus="Narnia", mw=10)
    with pytest.raises(ToolError, match="API respondió 409"):
        tools.remove_element("R1")  # base elements are never deleted


def test_join_session_picks_up_an_existing_one(tools, http):
    sid = tools.start_session()["session_id"]
    tools.start_run(horizon=4)
    other = Sub50Tools(Sub50Client(http=http), McpState())
    joined = other.join_session(sid)
    assert joined["session_id"] == sid and other.state.run_id == tools.state.run_id
    assert tools.end_session() == {"deleted": True}
    assert http.get(f"/api/v1/sessions/{sid}").status_code == 404


def test_the_server_lists_every_tool_with_the_guardrails(tools):
    server = build_server(tools)

    async def go():
        listed = await server.list_tools()
        result = await server.call_tool("start_session", {})
        return listed, result

    listed, result = asyncio.run(go())
    assert [t.name for t in listed] == list(TOOLS)
    assert all(t.description for t in listed)
    assert "does the most damage" in INSTRUCTIONS and "never the" in INSTRUCTIONS
    assert json.loads(result.content[0].text)["session_id"]


def test_every_tool_maps_to_an_operation_of_the_agent_spec():
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    ids = {op["operationId"] for path in spec["paths"].values() for op in path.values()}
    used = {op for ops in OPERATIONS.values() for op in ops}
    assert used <= ids, used - ids


def test_an_edit_separates_new_overloads_from_ones_already_there(tools):
    tools.start_session()
    before = tools.describe_network()["baseline"]["overloaded_lines"]
    base = tools.add_datacenter(bus="B002", mw=1000, name="DC grande")["baseline"]
    assert set(base["newly_overloaded"]) == set(base["overloaded_lines"]) - set(before)
    assert set(base["no_longer_overloaded"]) == set(before) - set(base["overloaded_lines"])
    assert base["newly_overloaded"], "a 1000 MW datacenter on the toy grid should overload something"
    again = tools.edit_element("D001", {"mw": 1000})["baseline"]
    assert again["newly_overloaded"] == []  # nothing changed, so nothing is new
