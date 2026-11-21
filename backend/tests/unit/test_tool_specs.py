"""Tool schemas for direct LLM tool calling, and the in-process transport (docs/assistant.md)."""

import json

import httpx
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from cascadasen.infrastructure.inprocess import in_process_client
from cascadasen.mcp.client import Sub50Client
from cascadasen.mcp.specs import tool_specs
from cascadasen.mcp.tools import TOOLS, Sub50Tools


def specs(exclude=frozenset()):
    tools = Sub50Tools(Sub50Client(http=httpx.Client(base_url="http://x")))
    return {s.name: s for s in tool_specs(tools, exclude)}


def test_every_tool_gets_a_described_object_schema():
    found = specs()
    assert list(found) == list(TOOLS)
    for spec in found.values():
        assert spec.description and spec.schema["type"] == "object"


def test_excluded_tools_are_left_out():
    assert "end_session" not in specs(frozenset({"end_session"}))


def test_required_arguments_and_cleaned_types():
    found = specs()
    assert found["cut_lines"].schema["required"] == ["lines"]
    assert found["start_session"].schema.get("required", []) == []
    dump = json.dumps({n: s.schema for n, s in found.items()})
    assert '"title"' not in dump and '"null"' not in dump and '"default"' not in dump
    assert found["add_datacenter"].schema["properties"]["mw"]["type"] == "number"
    assert found["start_run"].schema["properties"]["policy"]["enum"] == ["A", "B", "C"]
    assert found["start_session"].schema["properties"]["point"]["type"] == "string"


def test_the_in_process_client_reaches_the_app_with_the_callers_address():
    app = FastAPI()

    @app.get("/ping")
    def ping(request: Request):
        return {"host": request.client.host, "agent": request.headers.get("x-sub50-agent")}

    @app.get("/outer")
    def outer():  # a `def` route runs in a worker thread, as the assistant's chat route will
        client = Sub50Client(http=in_process_client(app, "203.0.113.9"), agent="asistente")
        client.api = ""
        return client.get("/ping")

    out = TestClient(app).get("/outer").json()
    assert out == {"host": "203.0.113.9", "agent": "asistente"}
