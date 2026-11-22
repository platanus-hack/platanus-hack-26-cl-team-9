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


def test_resolve_bus_by_id_and_exact_name_here_and_the_rest_on_the_server():
    assert digest.resolve_bus(NET, "b001") == ("B001", "barra indicada por id")
    assert digest.resolve_bus(NET, "alpha")[0] == "B000"  # "S/E Alpha" of this session
    with pytest.raises(ToolError, match="No pude elegir"):
        digest.resolve_bus(NET, "Iquique")  # no client: a city is not resolved locally

    class Places:
        def get(self, path, **params):
            assert path == "/grids/places" and params == {"q": "Iquique", "point": "nov2026-1300"}
            return {"bus": "B058", "how": "subestación que abastece a la comuna de Iquique"}

    assert digest.resolve_bus(NET, "Iquique", Places()) == (
        "B058",
        "subestación que abastece a la comuna de Iquique",
    )


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


def test_focus_digest_totals_and_overloaded_lines_of_the_area():
    net = {**NET, "baseline": {**NET["baseline"], "overloaded": ["R000"]}}
    out = digest.focus_digest(net, "antofagasta")
    assert out["area"] == "A02" and out["area_name"] == "Antofagasta"
    assert out["load_mw"] == 5.0 and out["gen_mw"] == 20.0 and out["overloaded_lines"] == ["R000"]


def test_snapshot_digest_computes_unserved_power_and_the_level_label():
    snap = {
        "cycle": 1,
        "metrics": {"demand_mw": 100.0, "served_mw": 75.5, "level": "L1", "people_without_power": 12.7},
    }
    out = digest.snapshot_digest(snap)
    assert (
        out["unserved_mw"] == 24.5
        and out["level_text"] == "L1 · contenido"
        and out["people_without_power"] == 13
    )
    rep = digest.report_digest({"consequence": {"worst_level": "L2"}, "indicators": {}})
    assert rep["consequence"]["worst_level_text"] == "L2 · apagón regional"


def test_incident_tools_list_the_catalog_and_start_a_run_without_ids_in_the_answer():
    seen = []

    def handler(request):
        seen.append((request.method, request.url.path, request.content))
        if request.url.path.endswith("/attacks/catalog"):
            return httpx.Response(
                200,
                json={
                    "notices": ["n"],
                    "cost_basis": {
                        "blackout_restoration_h": {"value": 7.34, "source": "[44]", "is_assumption": False}
                    },
                    "incidents": [
                        {
                            "id": "huatacondo-2026",
                            "title": "Huatacondo",
                            "date": "2026-08-26",
                            "kind": "cyber_documented",
                            "verified": True,
                            "notes": [],
                            "sources": [{"label": "x", "url": "https://x"}],
                            "effects": [{"cycle": 2, "type": "C1_generation_loss", "target": "A01"}],
                        }
                    ],
                },
            )
        return httpx.Response(201, json={"run_id": "r1", "template": "huatacondo-2026", "policy": "C"})

    tools = Sub50Tools(client_for(handler), McpState(session_id="s"))
    cat = tools.list_incident_scenarios()
    assert cat["incidents"][0]["effects"] == ["ciclo 2: C1_generation_loss en A01"]
    run = tools.start_incident_run("huatacondo-2026", seed=6)
    assert tools.state.run_id == "r1" and run["scenario_notices"][0].startswith("Escenario hipotético")
    assert b'"seed":6' in seen[-1][2].replace(b" ", b"") and seen[-1][1].endswith("/s/attacks/runs")
