"""Session overlay on the toy mapa 3 network: validation, ids and the rebalance rule."""

from typing import get_args

import pytest

from cascadasen.api.session_schemas import LoadKind, Tech
from cascadasen.domain.cascade import overlay as ov
from cascadasen.domain.cascade.engine import run_cascade_workflow
from cascadasen.domain.theater.areas import build_theater_network


@pytest.fixture
def base(toy_world):
    net, point = toy_world.load("nov2026-1300")
    return net.buses, point


def _add(o, kind, fields, base):
    return ov.add(o, kind, fields, *base)


def test_an_empty_overlay_is_identity(base):
    net, point = base
    applied = ov.apply_overlay(net, point, ov.empty_overlay())
    assert applied.net is net and applied.point is point
    assert applied.warnings == [] and applied.balance == []


def test_a_datacenter_is_rebalanced_over_the_synchronous_units(base):
    net, point = base
    o, load_id = _add(
        ov.empty_overlay(), "load", {"bus": "B002", "mw": 100, "kind": "datacenter", "name": "DC"}, base
    )
    assert load_id == "D001"
    applied = ov.apply_overlay(net, point, o)
    p = applied.point
    assert p.load[2] == pytest.approx(point.load[2] + 100)
    extra = p.gen - point.gen
    assert extra[0] == pytest.approx(100 * 300 / 550) and extra[4] == pytest.approx(100 * 250 / 550)
    assert (p.sync_mw - point.sync_mw)[[0, 4]] == pytest.approx(extra[[0, 4]])
    assert (p.inertia_mws == point.inertia_mws).all()
    assert abs(p.gen.sum() - p.load.sum()) < 1e-6
    [entry] = applied.balance
    assert entry["is_assumption"] is True and entry["redispatch_mw"] == pytest.approx(100)
    assert set(entry["buses"]) == {"B000", "B004"}
    summary = run_cascade_workflow(applied.net, p, [])["summary"]
    assert summary["load_shed_mw"] == 0
    assert all(i["result"] == "maintains" for i in summary["islands"])


def test_new_bus_and_line_ids_resolve_in_the_theatre(base, toy_spec):
    net, point = base
    o, bid = _add(ov.empty_overlay(), "bus", {"name": "Nueva", "lat": -31.1, "lon": -71.0, "kv": 220}, base)
    o, lid = _add(o, "line", {"a": "B002", "b": bid, "kv": 220, "capacity_mw": 300}, base)
    assert (bid, lid) == ("B006", "U001")
    applied = ov.apply_overlay(net, point, o)
    assert applied.net.size == 7 and applied.net.lines[-1].x_pu >= 5e-4
    theatre = build_theater_network(applied.net, applied.point.people, applied.point.load, toy_spec)
    assert theatre.resolve("B006").kind == "bus"
    assert theatre.resolve("U001").kind == "line"


@pytest.mark.parametrize(
    ("kind", "fields"),
    [
        ("line", {"a": "B000", "b": "B001", "kv": 400, "capacity_mw": 100, "x_pu": 0.01}),
        ("line", {"a": "B001", "b": "B001", "kv": 220, "capacity_mw": 100, "x_pu": 0.01}),
        ("load", {"bus": "B099", "mw": 10, "kind": "consumo", "name": "x"}),
        ("load", {"bus": "B001", "mw": 0, "kind": "consumo", "name": "x"}),
    ],
)
def test_invalid_edits_raise(base, kind, fields):
    with pytest.raises(ov.OverlayError):
        _add(ov.empty_overlay(), kind, fields, base)


def test_a_bus_without_lines_is_reported_isolated(base):
    net, point = base
    o, bid = _add(ov.empty_overlay(), "bus", {"name": "Sola", "lat": -31.1, "lon": -71.0, "kv": 220}, base)
    warnings = ov.apply_overlay(net, point, o).warnings
    assert {"code": "isolated_bus", "ids": [bid]} == {k: warnings[0][k] for k in ("code", "ids")}


def test_base_lines_are_taken_out_of_service_not_removed(base):
    net, point = base
    with pytest.raises(ov.OverlayError) as err:
        ov.remove(ov.empty_overlay(), "line", "R1", *base)
    assert err.value.conflict
    o = ov.patch(ov.empty_overlay(), "line", "R1", {"in_service": False}, *base)
    assert "R1" not in {ln.id for ln in ov.apply_overlay(net, point, o).net.lines}


def test_a_removed_session_bus_keeps_later_ids(base):
    net, point = base
    o, first = _add(ov.empty_overlay(), "bus", {"name": "A", "lat": -31.1, "lon": -71.0, "kv": 220}, base)
    o, line = _add(o, "line", {"a": "B002", "b": first, "kv": 220, "capacity_mw": 300}, base)
    with pytest.raises(ov.OverlayError) as err:
        ov.remove(o, "bus", first, *base)
    assert err.value.conflict and line in err.value.valid
    o = ov.remove(o, "line", line, *base)
    o = ov.remove(o, "bus", first, *base)
    o, second = _add(o, "bus", {"name": "B", "lat": -31.1, "lon": -71.0, "kv": 220}, base)
    assert (first, second) == ("B006", "B007")
    o, _ = _add(o, "line", {"a": "B002", "b": second, "kv": 220, "capacity_mw": 300}, base)
    applied = ov.apply_overlay(net, point, o)
    assert applied.net.size == 8 and applied.warnings == []
    with pytest.raises(ov.OverlayError) as err:
        ov.patch(o, "bus", first, {"name": "otra"}, *base)
    assert err.value.not_found


def test_an_out_of_service_bus_is_redispatched_in_its_island(base):
    net, point = base
    o = ov.patch(ov.empty_overlay(), "bus", "B001", {"in_service": False}, *base)  # not a cut vertex
    applied = ov.apply_overlay(net, point, o)
    p = applied.point
    assert p.load[1] == 0 and abs(p.gen.sum() - p.load.sum()) < 1e-6
    [entry] = applied.balance
    assert entry["redispatch_mw"] == pytest.approx(-100) and set(entry["buses"]) == {"B000", "B004"}
    assert applied.warnings == []
    summary = run_cascade_workflow(applied.net, p, [])["summary"]
    assert summary["load_shed_mw"] == 0
    assert all(i["result"] == "maintains" for i in summary["islands"])


def test_an_out_of_service_cut_vertex_keeps_the_split_imbalance(base):
    net, point = base
    o = ov.patch(ov.empty_overlay(), "bus", "B004", {"in_service": False}, *base)  # isolates B005
    applied = ov.apply_overlay(net, point, o)
    assert applied.balance == []
    codes = {(w["code"], tuple(w["ids"])) for w in applied.warnings}
    assert ("unbalanced_island", ("B005",)) in codes
    assert not any("B004" in w["ids"] for w in applied.warnings)


def test_a_generation_override_is_not_redispatched_back(base):
    net, point = base
    o = ov.patch(ov.empty_overlay(), "bus", "B000", {"gen_mw": 600, "sync_mw": 500}, *base)
    applied = ov.apply_overlay(net, point, o)
    p = applied.point
    assert p.gen[0] == pytest.approx(600) and p.gen[4] == pytest.approx(50)
    assert set(applied.balance[0]["buses"]) == {"B004"}


@pytest.mark.parametrize(
    "fields",
    [
        {"load_mw": 1e9},
        {"load_mw": 150 + 3001},
        {"inertia_mws": 10 * 300 + 1},
        {"load_mw": 150 + 2900, "gen_mw": 400 + 2200, "sync_mw": 300},  # 5100 MW changed
    ],
)
def test_bus_overrides_are_bounded(base, fields):
    with pytest.raises(ov.OverlayError):
        ov.patch(ov.empty_overlay(), "bus", "B000", fields, *base)


def test_session_schema_literals_match_the_overlay_sets():
    assert set(get_args(Tech)) == ov.TECHS
    assert set(get_args(LoadKind)) == ov.LOAD_KINDS
