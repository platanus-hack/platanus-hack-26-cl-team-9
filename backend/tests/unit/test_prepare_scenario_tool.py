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


def test_a_change_that_touched_nothing_carries_a_warning_and_small_ones_say_where():
    from cascadasen.mcp.digest import prepare_digest

    out = prepare_digest(
        {
            **PREPARED,
            "changes": [
                {"target": "generation", "matched": 0, "elements": []},
                {"target": "demand", "matched": 1, "elements": [{"id": "B010", "name": "S/E ANTOFAGASTA"}]},
            ],
        }
    )
    nothing, one = out["changes"]
    assert "no digas que se aplicó" in nothing["warning"]
    assert one["at"] == ["B010 S/E ANTOFAGASTA"] and "warning" not in one


def test_technology_names_people_use_are_mapped_and_nuclear_is_said_to_be_an_assumption():
    calls = []
    change = {"target": "generation", "places": ["Mejillones"], "tech": ["Nuclear"], "add": 500}
    out = tools_logging(calls).prepare_scenario([change, {**change, "tech": ["eólica", "BESS"]}])
    sent = calls[0][1]["changes"]
    assert sent[0]["tech"] == ["termica"] and sent[1]["tech"] == ["eolica", "bateria"]
    assert out["scenario"]["changes"] == sent  # the web loads what was really sent
    assert "térmica sincrónica" in out["notes"][0]


def test_the_digest_says_which_substation_a_change_created():
    from cascadasen.mcp.digest import prepare_digest

    out = prepare_digest(
        {
            "changes": [
                {
                    "target": "substation",
                    "matched": 1,
                    "new_substation": True,
                    "connects_to": ["B105", "B068"],
                    "places": [{"bus": "B105"}],
                    "elements": [{"id": "B188", "name": "S/E Solar Vallenar", "kv": 220.0}],
                }
            ],
            "totals": {},
            "overloaded_lines": [],
            "should_feed": {"by_zone": {}},
            "per_capita_w": 1,
            "assumptions": [],
        }
    )
    assert out["changes"][0]["created"] == "B188 S/E Solar Vallenar (220 kV), conectada a B105, B068"
