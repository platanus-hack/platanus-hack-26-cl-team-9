"""Documented-incident scenarios (docs/attack-sim.md): catalog valid against the mapa 3 network, V10
(Huatacondo gives L0/L1), reproducible by seed, and the guardrails of cyber.md 8. Real data."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from cascadasen.api.app import create_app
from cascadasen.application.theater_world import default_world
from cascadasen.domain.theater.catalog import ACTIONS, EVENTS
from cascadasen.domain.theater.config import theater_config
from cascadasen.domain.theater.cycle import RunConfig, Simulation
from cascadasen.domain.theater.incident import NOTICES, incident_catalog
from cascadasen.domain.theater.narrative import templates
from cascadasen.infrastructure.settings import REPO_ROOT

PROCESSED = REPO_ROOT / "data/processed"
pytestmark = pytest.mark.skipif(not (PROCESSED / "grid_snapshot.json").exists(), reason="no processed data")
IDS = ["huatacondo-2026", "polonia-2025", "reino-unido-2026", "25f-referencia"]
# techniques, vectors and products never appear (cyber.md 8); also no "hack" language in the UI text
FORBIDDEN = re.compile(
    r"hacke|malware|ransomware|phishing|exploit|cve-|credential|password|contraseña|scada|modbus|dnp3|"
    r"iec ?104|firmware|vulnerab|botnet|backdoor",
    re.IGNORECASE,
)


@pytest.fixture(scope="module")
def world():
    return default_world(str(PROCESSED))


def run(world, scenario: str, seed: int = 1, stochastic: bool = False, **kw):
    # scripted by default, like the API: the card must be the incident's own, not the theatre's chance
    sim = Simulation(world, RunConfig(template=scenario, policy="C", seed=seed, stochastic=stochastic, **kw))
    while not sim.finished:
        sim.step()
    return sim


def test_the_catalog_is_bounded_curated_and_has_sources():
    cfg = theater_config()
    assert list(cfg.incidents) == IDS
    for inc in cfg.incidents.values():
        assert inc.sources and all(s["url"] and s["label"] for s in inc.sources)
        assert set(inc.mitigations) <= set(ACTIONS)
        t = cfg.templates[inc.id]
        assert t.adversary["enabled"] is False  # the incident is the script
    assert cfg.incidents["reino-unido-2026"].verified is False  # press-based, flagged
    assert cfg.incidents["25f-referencia"].kind == "reference_not_cyber"


def test_every_scenario_effect_resolves_on_the_real_network(world):
    cfg = theater_config()
    net, _ = world.load("nov2026-1300")
    for iid in IDS:
        for e in cfg.templates[iid].scenario_events:
            spec = EVENTS[e["type"]]
            if "zone" in spec.targets and e["target"] in {a.zone for a in net.areas.values()}:
                continue
            assert net.resolve(e["target"]) is not None, (iid, e)
        Simulation(world, RunConfig(template=iid, seed=1))  # validates every scheduled event


def test_v10_huatacondo_is_absorbed_or_contained(world):
    for seed in range(1, 9):
        rep = run(world, "huatacondo-2026", seed).report()
        assert rep["consequence"]["worst_level"] in {"L0", "L1"}
        card = rep["incident"]["consequence_card"]
        assert card["consequence_level"] in {"L0", "L1"} and card["notices"] == list(NOTICES)


def test_a_scripted_incident_has_no_unplanned_events_so_the_small_ones_stay_small(world):
    # with the theatre's chance on, seed 6 added an unplanned demand surge and renewable drop and made the
    # 40 MW UK counter-example an L2; the card would then blame the incident for events it did not script
    for scenario in ("reino-unido-2026", "huatacondo-2026"):
        for seed in range(1, 9):
            sim = run(world, scenario, seed)
            sources = {e["source"] for s in sim.snapshots for e in s["events"]}
            assert sources <= {"scenario"}, (scenario, seed, sources)
            assert sim.report()["incident"]["consequence_card"]["consequence_level"] == "L0", (scenario, seed)


def test_the_card_cost_is_the_calibrated_one_of_estado_de_la_red(world):
    card = run(world, "25f-referencia", 1).report()["incident"]["consequence_card"]
    # [44] ISCI for Enel Foundation: about US$ 984 M and 81,430 MWh for the 25F (docs/engine.md "Cost", #82)
    assert card["failure_cost_usd"] == pytest.approx(984e6, rel=0.01)
    assert card["unserved_energy_mwh"] == pytest.approx(81430, rel=0.01)
    assert card["outage_duration_h"] == {"value": 7.34, "is_assumption": False}
    basis = card["cost_basis"]
    assert basis["blackout_restoration_h"]["source"] and basis["shed_restoration_h"]["is_assumption"] is True


def test_a_shed_only_incident_pays_one_assumed_hour_and_no_total_blackout_premium(world):
    card = run(world, "polonia-2025", 5).report()["incident"]["consequence_card"]
    assert card["outage_duration_h"] == {"value": 1.0, "is_assumption": True}
    assert card["cost_breakdown"]["dark_mw"] == 0 and card["cost_breakdown"]["total_blackout_factor"] == 1.0
    assert card["failure_cost_usd"] == pytest.approx(card["cost_per_hour_usd"], rel=0.01)
    assert card["load_shed_mw"] > 0 and card["people_without_power"] > 0


def test_an_absorbed_incident_costs_nothing(world):
    card = run(world, "huatacondo-2026", 1).report()["incident"]["consequence_card"]
    assert card["failure_cost_usd"] == 0 and card["unserved_energy_mwh"] == 0


def test_the_25f_reference_cascades_but_is_labelled_not_cyber(world):
    rep = run(world, "25f-referencia", 1).report()
    assert rep["consequence"]["worst_level"] in {"L2", "L3"}
    assert rep["incident"]["kind"] == "reference_not_cyber"


def test_a_replay_with_the_same_seed_is_identical(world):
    a, b = run(world, "polonia-2025", 9), run(world, "polonia-2025", 9)
    assert a.report()["trace_head"] == b.report()["trace_head"]
    assert a.report()["incident"] == b.report()["incident"]
    assert RunConfig.from_dict(json.loads(json.dumps(a.config.as_dict()))) == a.config


def test_after_action_describes_effects_and_prevention_in_spanish(world):
    from cascadasen.domain.theater.narrative import TemplateInterpreter

    sim = run(world, "polonia-2025", 2)
    aar = TemplateInterpreter().after_action(sim.report(), sim.snapshots)["incident"]
    assert aar["prevention"] and all(p and p in templates()["prevention"].values() for p in aar["prevention"])
    assert "supuesto" in aar["effect"] and aar["sources"] and aar["notices"] == list(NOTICES)


def test_guardrails_no_technique_no_ranking_no_named_plants():
    cat = incident_catalog(theater_config())
    text = (
        json.dumps(cat, ensure_ascii=False)
        + (REPO_ROOT / "backend/src/cascadasen/domain/theater/params/incidents.yaml").read_text()
    )
    assert not FORBIDDEN.search(text)
    for e in (e for i in cat["incidents"] for e in i["effects"]):
        assert not re.search(r"P\d{3}|SE\d{3}", e["target"])  # areas, zones and corridors only
    assert [i["id"] for i in cat["incidents"]] == IDS  # file order, never sorted by damage
    narr = json.dumps(templates(), ensure_ascii=False)
    assert not re.search(r"hackear|atacar la red", narr, re.IGNORECASE)


def test_the_api_launches_a_run_inside_a_session_and_rejects_unknown_ids():
    c = TestClient(create_app())
    cat = c.get("/api/v1/attacks/catalog").json()
    assert [i["id"] for i in cat["incidents"]] == IDS and cat["cost_basis"]["blackout_restoration_h"][
        "value"
    ] == 7.34
    sid = c.post("/api/v1/sessions", json={}).json()["session_id"]
    bad = c.post(f"/api/v1/sessions/{sid}/attacks/runs", json={"scenario": "cualquiera"})
    assert bad.status_code == 422 and bad.json()["detail"]["valid"] == IDS
    r = c.post(f"/api/v1/sessions/{sid}/attacks/runs", json={"scenario": "huatacondo-2026", "seed": 4})
    assert r.status_code == 201 and r.json()["session_revision"] >= 1
    rid = r.json()["run_id"]
    assert c.get(f"/api/v1/sessions/{sid}/runs/{rid}/trace").json()["recipe"]["config"]["stochastic"] is False
    assert c.post(f"/api/v1/sessions/{sid}/runs/{rid}/step", json={"cycles": 24}).status_code == 200
    rep = c.get(f"/api/v1/sessions/{sid}/runs/{rid}/report").json()
    assert rep["incident"]["id"] == "huatacondo-2026" and rep["incident"]["adversary"] is False
    aar = c.get(f"/api/v1/sessions/{sid}/runs/{rid}/after_action").json()
    assert "incident" in aar


def test_the_incident_point_must_match_the_session_point():
    c = TestClient(create_app())
    sid = c.post("/api/v1/sessions", json={"point": "nov2026-1300"}).json()["session_id"]
    bad = c.post(f"/api/v1/sessions/{sid}/attacks/runs", json={"scenario": "25f-referencia", "seed": 1})
    assert bad.status_code == 422
    assert bad.json()["detail"]["field"] == "scenario" and bad.json()["detail"]["valid"] == ["feb2025-1500"]
    sid = c.post("/api/v1/sessions", json={"point": "feb2025-1500"}).json()["session_id"]
    ok_ = c.post(f"/api/v1/sessions/{sid}/attacks/runs", json={"scenario": "25f-referencia", "seed": 1})
    assert ok_.status_code == 201 and ok_.json()["operating_point"] == "feb2025-1500"
