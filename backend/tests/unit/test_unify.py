from cascadasen.application.grid_queries import GridQueryService
from cascadasen.domain.model import EdgeKind, NodeKind
from cascadasen.domain.validation import validate_snapshot


def by_name(snapshot, name):
    return next(n for n in snapshot.nodes if n.name == name)


def test_substations_join_ide_and_cen_by_id(toy_snapshot):
    beta = by_name(toy_snapshot, "S/E BETA")
    assert beta.id == "SE102"
    assert beta.ids["cen_code"] == "SE002T0001"
    assert beta.kv_levels == [500.0, 220.0]  # busbar adds the 220 kV level


def test_geometric_lines_connect_named_substations(toy_snapshot):
    lines = {e.ids.get("ide_objectid"): e for e in toy_snapshot.edges if e.kind == EdgeKind.LINE}
    assert {lines["11"].source_node, lines["11"].target_node} == {"SE101", "SE102"}
    assert {lines["12"].source_node, lines["12"].target_node} == {"SE102", "SE103"}


def test_cen_section_confirms_existing_edge_and_adds_missing_one(toy_snapshot):
    s = toy_snapshot.stats["cen_sections"]
    assert s["confirmed_direct"] == 1  # ALFA-BETA has IDE geometry
    assert s["added_from_cen"] == 1  # BETA-DELTA only exists in the CEN registry
    added = next(e for e in toy_snapshot.edges if e.id == "T901")
    assert {added.source_node, added.target_node} == {"SE102", "SE104"}
    assert added.geometry_source.startswith("recta")
    confirmed = next(e for e in toy_snapshot.edges if e.ids.get("ide_objectid") == "11")
    assert confirmed.ids["cen_tramos"][0]["cen_tramo_id"] == "900"


def test_electrical_parameters_attached_from_model(toy_snapshot):
    e = next(e for e in toy_snapshot.edges if e.ids.get("ide_objectid") == "11")
    assert e.electrical is not None
    assert e.electrical.s_nom_mva == 2000.0
    assert e.electrical.x_ohm == 30.0


def test_plant_uses_declared_model_bus(toy_snapshot):
    p = next(p for p in toy_snapshot.plants if p.name == "ALFA")
    assert p.node == "SE101"
    assert p.connection_method == "barra declarada en PyPSA-CL"
    assert p.inertia_s == 4.0
    assert by_name(toy_snapshot, "S/E ALFA").generation_mw == 300.0


def test_population_is_fully_assigned_to_delivery_substations(toy_snapshot):
    total = sum(n.served_population for n in toy_snapshot.nodes)
    assert round(total) == 1500
    gamma = next(c for c in toy_snapshot.comunas if c.cut == "5101")
    assert gamma.served_by[0].node == "SE103"
    nodes = {n.id: n for n in toy_snapshot.nodes}
    assert all(nodes[s.node].delivers for s in gamma.served_by)


def test_islands_when_cutting_the_only_link(toy_snapshot):
    q = GridQueryService(toy_snapshot)
    cut = next(e.id for e in toy_snapshot.edges if e.ids.get("ide_objectid") == "12")  # BETA-GAMMA
    r = q.islands([cut])
    assert r["new_islands"] == 1
    island = r["islands"][1]
    assert "SE103" in island["node_ids"]
    assert island["generation_mw"] == 50.0  # SOLAR GAMMA keeps the island alive
    assert r["population_without_supply"] == 0


def test_path_and_neighbors(toy_snapshot):
    q = GridQueryService(toy_snapshot)
    p = q.path("SE101", "SE103")
    assert p["found"] and [n["id"] for n in p["nodes"]] == ["SE101", "SE102", "SE103"]
    nb = q.neighbors("SE102")
    assert {n["id"] for n in nb["nodes"]} >= {"SE101", "SE103", "SE104"}


def test_validation_runs_and_reports_statuses(toy_snapshot):
    v = validate_snapshot(toy_snapshot)
    ids = {c["id"]: c for c in v["checks"]}
    assert ids["population_assigned"]["status"] == "ok"
    assert ids["comuna_consistency"]["status"] in {"ok", "warn"}
    assert all(c["status"] in {"ok", "warn", "fail"} for c in v["checks"])


def test_no_unlocated_substation_in_toy(toy_snapshot):
    assert all(n.located for n in toy_snapshot.nodes if n.kind == NodeKind.SUBSTATION)
