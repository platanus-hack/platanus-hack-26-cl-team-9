"""The assistant's prepare_scenario tool sets the final grid and, with failures, simulates it (docs/stress.md)."""

import json

import httpx

from cascadasen.mcp.client import Sub50Client
from cascadasen.mcp.state import McpState
from cascadasen.mcp.tools import Sub50Tools

SIM = {
    "timeline": {
        "summary": {"people_without_power": 7, "load_shed_mw": 3, "dark_load_mw": 1},
        "events": [{"type": "line_overload_open", "ids": ["R002"]}],
    },
    "supply": {"by_zone": {"CE": {"should_feed": 10, "feeds": 7, "pct_fed": 70.0}}},
}
PREPARED = {
    "changes": [{"target": "population", "matched": 1, "elements": []}],
    "totals": {},
    "overloaded_lines": [],
    "should_feed": {"by_zone": {}},
    "per_capita_w": 238.0,
    "assumptions": [{"text": "a"}],
}


def tools_logging(calls: list) -> Sub50Tools:
    def handler(request):
        body = json.loads(request.content or b"{}")
        calls.append((request.url.path, body))
        return httpx.Response(200, json=PREPARED if request.url.path.endswith("/prepare") else SIM)

    http = httpx.Client(base_url="http://api", transport=httpx.MockTransport(handler))
    return Sub50Tools(Sub50Client(http=http, agent="tester"), McpState())


def test_changes_and_failures_prepare_then_simulate_against_the_base():
    calls = []
    change = {"target": "population", "comunas": ["13201"], "factor": 3}
    out = tools_logging(calls).prepare_scenario([change], open_lines=["R239"])
    assert [p.rsplit("/", 1)[-1] for p, _ in calls] == ["prepare", "simulate", "simulate"]
    assert calls[1][1]["changes"] == [change] and "changes" not in calls[2][1]  # the second one is the base
    assert out["scenario"] == {
        "point": "nov2026-1300",
        "changes": [change],
        "open_lines": ["R239"],
        "out_buses": [],
    }
    assert out["simulation"]["lines_opened_by_cascade"] == ["R002"]
    assert "elements" not in out["prepared"]["changes"][0]


def test_without_failures_nothing_is_simulated():
    calls = []
    out = tools_logging(calls).prepare_scenario([{"target": "demand", "zones": ["NG"], "add": 100}])
    assert [p.rsplit("/", 1)[-1] for p, _ in calls] == ["prepare"] and "simulation" not in out
