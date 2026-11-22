"""MCP client and digests against canned HTTP responses (docs/mcp.md)."""

import json

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


def test_focus_digest_accepts_a_bus_id_or_a_part_of_a_bus_name_and_names_the_valid_areas_on_a_miss():
    by_id = digest.focus_digest(NET, "b001")
    assert by_id["area"] is None and [b["id"] for b in by_id["buses"]] == ["B001"]
    by_name = digest.focus_digest(NET, "beta")
    assert [b["id"] for b in by_name["buses"]] == ["B001"] and by_name["lines"][0]["id"] == "R000"
    with pytest.raises(ToolError, match=r"No encuentro 'nada'.*A01, A02"):
        digest.focus_digest(NET, "nada")


def test_events_applied_lists_the_events_and_warns_when_there_are_none():
    snaps = [
        {"cycle": 1, "events": [{"type": "C3_transmission_opening", "target": "A06-A07"}]},
        {"cycle": 2, "events": [{"type": "D1_telemetry_loss", "area": "A02"}]},
    ]
    out = digest.events_applied(snaps)
    assert out["events_applied"] == [
        {"cycle": 1, "type": "C3_transmission_opening", "target": "A06-A07"},
        {"cycle": 2, "type": "D1_telemetry_loss", "target": "A02"},
    ]
    assert "warning" not in out
    empty = digest.events_applied([{"cycle": 1, "events": []}])
    assert empty["events_applied"] == [] and "inject_event" in empty["warning"]


def test_report_digest_adds_the_incident_section_only_when_the_run_has_one():
    plain = digest.report_digest({"indicators": {}})
    assert "incident" not in plain and plain["notice"] == digest.NOTICE
    inc = {"id": "huatacondo-2026", "title": "Huatacondo", "mitigations": ["m"], "internal": "dropped"}
    out = digest.report_digest({"indicators": {}, "incident": inc})
    assert out["incident"] == {"id": "huatacondo-2026", "title": "Huatacondo", "mitigations": ["m"]}


def test_prepare_digest_names_at_most_five_substations_and_drops_the_per_substation_rows():
    digest_warning = digest.prepare_digest(
        {
            "changes": [{"matched": 0}],
            "totals": {},
            "overloaded_lines": [],
            "should_feed": {"by_zone": {}},
            "per_capita_w": 1,
            "assumptions": [],
        }
    )["changes"][0]["warning"]
    out = digest.prepare_digest(
        {
            "changes": [
                {
                    "target": "demand",
                    "count": 2,
                    "matched": 2,
                    "elements": [{"id": "B000", "name": "S/E A"}, {"id": "B001", "name": "S/E B"}],
                },
                {
                    "target": "generation",
                    "matched": 9,
                    "elements": [{"id": f"B{i:03d}", "name": "x"} for i in range(9)],
                },
                {"target": "generation", "matched": 0, "elements": []},
            ],
            "totals": {"load_mw": 15.0},
            "overloaded_lines": ["R000", "R001"],
            "should_feed": {"by_zone": {"NG": 30}},
            "per_capita_w": 500,
            "assumptions": [{"text": "a1"}, {"text": "a2"}],
        }
    )
    assert "no las compares" in out.pop("overloaded_lines_note")  # the count has no base to compare with
    assert out.pop("health") is None  # no health block in this response (#139 adds it to /grids/prepare)
    assert out == {
        "changes": [
            {"target": "demand", "count": 2, "matched": 2, "at": ["B000 S/E A", "B001 S/E B"]},
            {"target": "generation", "matched": 9},  # more than five: no list, no ranking of substations
            {
                "target": "generation",
                "matched": 0,
                "warning": digest_warning,
            },  # touched nothing: never "applied"
        ],
        "totals": {"load_mw": 15.0},
        "overloaded_lines": 2,
        "should_feed_by_zone": {"NG": 30},
        "per_capita_w": 500,
        "assumptions": ["a1", "a2"],
    }


def _simulation(people, shed, dark, opened):
    return {
        "timeline": {
            "summary": {"people_without_power": people, "load_shed_mw": shed, "dark_load_mw": dark},
            "events": [{"type": "line_overload_open", "ids": ids} for ids in opened]
            + [{"type": "island_formed", "ids": ["X9"]}],
        },
        "supply": {"by_zone": {"NG": {"should_feed": 10, "feeds": 8}}},
    }


def test_simulation_digest_compares_with_and_without_the_changes_and_lists_cascade_lines_sorted():
    out = digest.simulation_digest(
        _simulation(100, 50.0, 40.0, [["R2", "R1"], ["R1"]]), _simulation(10, 5.0, 4.0, [])
    )
    assert out["with_changes"] == {"people_without_power": 100, "load_shed_mw": 50.0, "dark_load_mw": 40.0}
    assert out["without_changes"] == {"people_without_power": 10, "load_shed_mw": 5.0, "dark_load_mw": 4.0}
    assert out["lines_opened_by_cascade"] == ["R1", "R2"]
    assert out["supply_by_zone"] == {"NG": {"should_feed": 10, "feeds": 8}}


def _recording(responses):
    """A client whose handler answers by path suffix and records (method, path, JSON body)."""
    seen = []

    def handler(request):
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path.removeprefix("/api/v1"), body))
        for suffix, payload in responses.items():
            if request.url.path.endswith(suffix):
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"detail": request.url.path})

    return client_for(handler), seen


EDIT = {"id": "X1", "warnings": ["w"], "balance": [{"redispatch_mw": 1, "rule": "r", "is_assumption": True}]}


def test_edit_tools_send_the_documented_body_and_report_the_baseline_change():
    net_over = {**NET, "baseline": {**NET["baseline"], "overloaded": ["R000"]}}
    places = {"bus": "B001", "how": "comuna de Antofagasta, servida por S/E B"}
    client, seen = _recording(
        {"/network": net_over, "/places": places, "/generators": EDIT, "/lines": EDIT, "/buses": EDIT}
    )
    tools = Sub50Tools(client, McpState(session_id="s"))
    gen = tools.add_generator("Antofagasta", 40, "solar")
    assert gen["bus"] == "B001" and gen["area_name"] == "Antofagasta" and gen["id"] == "X1"
    assert gen["placed"] == places["how"] and any(s[1].endswith("/grids/places") for s in seen)
    assert gen["baseline"]["still_overloaded"] == ["R000"] and gen["baseline"]["newly_overloaded"] == []
    assert seen[-2][2] == {"bus": "B001", "mw": 40, "tech": "solar"}  # no name key when it is None
    line = tools.add_line("B000", "B001", 220, 300, name="L nueva")
    assert seen[-2][2] == {"a": "B000", "b": "B001", "kv": 220, "capacity_mw": 300, "name": "L nueva"}
    assert line["redispatch"][0]["is_assumption"] is True and line["notice"] == digest.NOTICE
    tools.add_bus("S/E Nueva", -33.0, -70.0, 110)
    assert seen[-2][1].endswith("/sessions/s/buses")
    assert seen[-2][2] == {"name": "S/E Nueva", "lat": -33.0, "lon": -70.0, "kv": 110}


def test_add_substation_sends_each_connection_as_a_bus_id_string_and_resolves_places():
    # Regression (#124): `resolve_bus` returns (bus, how); the tuple went into `to` (422) and a place name
    # such as "Antofagasta" failed because the client was not passed.
    places = {"bus": "B001", "how": "comuna de Antofagasta, servida por S/E B"}
    client, seen = _recording({"/network": NET, "/places": places, "/substations": EDIT})
    tools = Sub50Tools(client, McpState(session_id="s"))
    tools.add_substation(
        "S/E Nueva",
        -28.6,
        -70.8,
        220,
        [{"to": "B000", "capacity_mw": 200}, {"to": "Antofagasta"}],
        generator_mw=120,
        generator_tech="solar",
    )
    body = next(b for m, path, b in seen if m == "POST" and path.endswith("/substations"))
    assert body["connections"] == [{"to": "B000", "capacity_mw": 200}, {"to": "B001"}]
    assert body["generator"] == {"mw": 120, "tech": "solar"}


def test_run_tools_send_the_adversary_the_share_and_report_the_status():
    run = {"run_id": "r1", "status": "running", "cycle": 3, "horizon": 8, "seed": 5}
    client, seen = _recording(
        {
            "/runs": run,
            "/events": {"accepted": True, "applies_at_cycle": 4, "resolved_target": "A01"},
            "/runs/r1": {"run": run, "latest": {"cycle": 3, "metrics": {}}, "resources": {"crews": 2}},
        }
    )
    tools = Sub50Tools(client, McpState(session_id="s"))
    started = tools.start_run(seed=5, adversary_objective="blackout", adversary_budget=3)
    assert tools.state.run_id == "r1" and started["notice"] == digest.NOTICE
    assert seen[-1][2] == {
        "template": "open_field",
        "policy": "C",
        "horizon": 24,
        "seed": 5,
        "adversary": {"enabled": True, "objective": "blackout", "budget": 3, "adaptive": True},
    }
    ev = tools.inject_event("C3_transmission_opening", "A01", share=0.5)
    assert seen[-1][2] == {"type": "C3_transmission_opening", "target": "A01", "params": {"share": 0.5}}
    assert ev["resolved_target"] == "A01" and ev["applies_at_cycle"] == 4
    status = tools.run_status()
    assert status["run"]["cycle"] == 3 and status["latest"]["cycle"] == 3
    assert status["resources"] == {"crews": 2}


def test_run_status_without_a_snapshot_returns_none_for_latest():
    client, _ = _recording({"/runs/r1": {"run": {"run_id": "r1"}, "latest": None}})
    out = Sub50Tools(client, McpState(session_id="s", run_id="r1")).run_status()
    assert out["latest"] is None and out["run"] == {"run_id": "r1"}


def test_list_options_keeps_ids_and_roles_only():
    catalog = {
        "operating_points": ["nov2026-1300"],
        "templates": [
            {
                "id": "open_field",
                "scenario_events": [],
                "adversary": {"enabled": False},
                "horizon": 24,
                "x": 1,
            }
        ],
        "policies": [{"id": "A", "name": "reactiva"}, {"id": "C", "name": "adaptativa"}],
        "events": [{"id": "C3_transmission_opening", "targets": ["corridor"], "defaults": {}, "extra": 1}],
        "actions": [{"id": "restore_element", "proposers": ["operations"], "target": "line", "extra": 1}],
        "objectives": ["blackout"],
    }
    client, _ = _recording({"/sim/catalog": catalog})
    out = Sub50Tools(client, McpState()).list_options()
    assert out["templates"] == [
        {"id": "open_field", "scripted_events": [], "adversary": False, "horizon": 24}
    ]
    assert out["policies"] == ["A", "C"]
    assert out["actions"] == [{"id": "restore_element", "roles": ["operations"], "target": "line"}]
    assert out["events"][0] == {"id": "C3_transmission_opening", "targets": ["corridor"], "defaults": {}}
    assert out["adversary_objectives"] == ["blackout"] and out["notice"] == digest.NOTICE


def test_prepare_scenario_works_without_a_session_and_only_calls_what_the_input_needs():
    prepared = {
        "changes": [{"target": "demand", "matched": 1, "elements": [{"id": "B000", "name": "S/E A"}]}],
        "totals": {},
        "overloaded_lines": [],
        "should_feed": {"by_zone": {}},
        "per_capita_w": 1,
        "assumptions": [],
    }
    client, seen = _recording(
        {"/grids/prepare": prepared, "/grids/simulate": _simulation(10, 1.0, 1.0, [["R1"]])}
    )
    tools = Sub50Tools(client, McpState())
    change = {"target": "demand", "factor": 2.0, "zones": ["NG"]}
    empty = tools.prepare_scenario()
    assert seen == [] and empty["scenario"]["point"] == "nov2026-1300" and "prepared" not in empty
    only_changes = tools.prepare_scenario(changes=[change], point="feb2025-1500")
    assert [s[1] for s in seen] == [
        "/grids/prepare",
        "/grids/simulate",
    ]  # changes alone: one run, no base run
    assert only_changes["simulation"]["without_changes"] == {
        "people_without_power": 0,
        "load_shed_mw": 0,
        "dark_load_mw": 0,
    }
    assert only_changes["prepared"]["changes"] == [{"target": "demand", "matched": 1, "at": ["B000 S/E A"]}]
    seen.clear()
    both = tools.prepare_scenario(changes=[change], open_lines=["R000"], out_buses=["B001"])
    assert [s[1] for s in seen] == ["/grids/prepare", "/grids/simulate", "/grids/simulate"]
    assert seen[1][2] == {
        "point": "nov2026-1300",
        "open_lines": ["R000"],
        "out_buses": ["B001"],
        "changes": [change],
    }
    assert "changes" not in seen[2][2]  # the base-grid run has the failures only
    assert both["simulation"]["lines_opened_by_cascade"] == ["R1"] and both["notice"] == digest.NOTICE
    seen.clear()
    tools.prepare_scenario(open_lines=["R000"])
    assert [s[1] for s in seen] == ["/grids/simulate"]  # no changes: one run serves as both sides


def test_find_line_asks_the_lines_route_and_needs_no_session():
    answer = {
        "query": "Ancoa – Alto Jahuel",
        "how": "h",
        "matched": 1,
        "lines": [{"id": "R006"}],
        "truncated": False,
    }

    def handler(request):
        assert request.url.path == "/api/v1/grids/lines"
        assert dict(request.url.params) == {"q": "Ancoa – Alto Jahuel", "point": "nov2026-1300"}
        return httpx.Response(200, json=answer)

    found = Sub50Tools(client_for(handler)).find_line("Ancoa – Alto Jahuel")  # no session in the state
    assert found["lines"] == [{"id": "R006"}] and found["notice"] == digest.NOTICE
