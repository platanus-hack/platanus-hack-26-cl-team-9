"""MCP client and digests against canned HTTP responses (docs/mcp.md)."""

import httpx
import pytest

pytest.importorskip("mcp")

from cascadasen.mcp import digest
from cascadasen.mcp.client import Sub50Client, ToolError
from cascadasen.mcp.state import McpState
from cascadasen.mcp.tools import OPERATIONS, Sub50Tools

NET = {
    "point": "nov2026-1300",
    "nodes": [
        {"id": "B000", "name": "S/E Alpha", "kv": 110, "area": "A01", "in_service": True},
        {"id": "B001", "name": "S/E Beta", "kv": 220, "area": "A02", "in_service": True},
    ],
    "lines": [{"id": "R000", "a": "B000", "b": "B001", "kv": 220, "capacity_mw": 300}],
    "buses": {
        "B000": {"load_mw": 10.0, "gen_mw": 0.0},
        "B001": {"load_mw": 5.0, "gen_mw": 20.0},
    },
    "areas": [
        {
            "id": "A01",
            "name": "Arica–Iquique",
            "zone": "NG",
            "population": 10,
            "buses": ["B000"],
            "anchor_bus": "B000",
        },
        {
            "id": "A02",
            "name": "Antofagasta",
            "zone": "NG",
            "population": 20,
            "buses": ["B001"],
            "anchor_bus": "B001",
        },
    ],
    "baseline": {"max_loading": 0.5, "overloaded": [], "islands": [{}], "load_shed_mw": 0},
}


def client_for(handler) -> Sub50Client:
    http = httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler))
    return Sub50Client(http=http, agent="tester")


def test_errors_carry_the_spanish_detail_and_valid_values():
    def handler(request):
        return httpx.Response(
            422, json={"detail": {"field": "tech", "message": "no existe", "valid": ["solar", "hidro"]}}
        )

    with pytest.raises(ToolError, match=r"tech: no existe.*solar"):
        client_for(handler).post("/sessions/x/generators", {})


def test_rate_limit_tells_the_model_to_wait():
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "12"}, json={"detail": "x"})

    with pytest.raises(ToolError, match="espera 12 segundos"):
        client_for(handler).get("/sessions/x")


def test_a_write_conflict_is_retried_once_and_reads_are_not():
    calls = []

    def handler(request):
        calls.append(request.method)
        if request.method == "POST" and calls.count("POST") == 1:
            return httpx.Response(409, json={"detail": "otra instancia"})
        return httpx.Response(200, json={"ok": True})

    c = client_for(handler)
    assert c.post("/sessions/x/cut", {"lines": ["R1"]}) == {"ok": True}
    assert calls == ["POST", "POST"]


def test_a_busy_session_is_retried_after_retry_after_for_reads_and_writes():
    calls, waits = [], []

    def handler(request):
        calls.append(request.method)
        if len(calls) % 2:
            return httpx.Response(
                409, headers={"Retry-After": "1"}, json={"detail": "La sesión está ocupada"}
            )
        return httpx.Response(200, json={"ok": True})

    http = httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler))
    c = Sub50Client(http=http, agent="tester", sleep=waits.append)
    assert c.get("/sessions/x/state") == {"ok": True}
    assert c.post("/sessions/x/cut", {"lines": ["R1"]}) == {"ok": True}
    assert calls == ["GET", "GET", "POST", "POST"] and waits == [1.0, 1.0]


def test_every_call_names_the_agent():
    seen = {}

    def handler(request):
        seen["agent"] = request.headers["X-Sub50-Agent"]
        return httpx.Response(200, json={})

    client_for(handler).get("/sim/catalog")
    assert seen["agent"] == "tester"


def test_resolve_bus_by_id_area_name_and_unique_bus_name():
    assert digest.resolve_bus(NET, "b001") == "B001"
    assert digest.resolve_bus(NET, "Antofagasta") == "B001"
    assert digest.resolve_bus(NET, "arica") == "B000"
    assert digest.resolve_bus(NET, "alpha") == "B000"
    with pytest.raises(ToolError, match="No pude elegir"):
        digest.resolve_bus(NET, "zzz")


def test_network_and_focus_digests_stay_small():
    overview = digest.network_digest(NET)
    assert overview["areas"][1]["load_mw"] == 5.0 and overview["bus_count"] == 2
    focus = digest.focus_digest(NET, "A01")
    assert [b["id"] for b in focus["buses"]] == ["B000"] and focus["lines"][0]["id"] == "R000"
    with pytest.raises(ToolError):
        digest.focus_digest(NET, "nada")


def test_cut_digest_keeps_the_notice_and_drops_frames():
    resp = {
        "open_lines": ["R1"],
        "timeline": {
            "frames": [1] * 500,
            "summary": {"load_shed_mw": 5, "islands": [{"result": "maintains", "x": 1}]},
        },
        "notice": "n",
    }
    out = digest.cut_digest(resp)
    assert out["load_shed_mw"] == 5 and out["notice"] == "n" and "frames" not in out
    assert out["islands"] == [{"result": "maintains"}]


def test_tools_need_a_session_first():
    tools = Sub50Tools(client_for(lambda r: httpx.Response(200, json={})), McpState())
    with pytest.raises(ToolError, match="start_session"):
        tools.cut_lines(["R1"])
    with pytest.raises(ToolError, match="id de elemento"):
        tools.state.session_id = "s"
        tools.edit_element("ZZ", {})


def test_there_is_no_tool_that_ranks_cuts():
    banned = ("worst", "rank", "optimi", "most_damage", "weakest", "critical")
    assert not [t for t in OPERATIONS if any(b in t for b in banned)]
