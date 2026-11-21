"""Spanish narration: every catalog item has a template, numbers use Spanish separators."""

from cascadasen.domain.theater.catalog import ACTIONS, EVENTS, OBJECTIVES
from cascadasen.domain.theater.config import theater_config
from cascadasen.domain.theater.narrative import num, pct, render, templates


def test_every_catalog_item_has_spanish_text():
    t = templates()
    assert set(EVENTS) <= set(t["event_types"])
    assert set(ACTIONS) <= set(t["actions"])
    assert set(OBJECTIVES) <= set(t["labels"])
    cfg = theater_config()
    assert {p.label_key for p in cfg.policies.values()} <= set(t["labels"])
    assert {tp.question_key for tp in cfg.templates.values()} <= set(t["questions"])


def test_render_and_spanish_numbers():
    assert render("actions", "backup_comms", {"target": "A09"}) == "Activar comunicaciones de respaldo en A09"
    assert render("events", "edac_step", {"step": 2, "mw": 340.0}).endswith("340 MW.")
    assert render("nope", "x") == "x"
    assert num(7752165.4) == "7.752.165" and num(8.79, 2) == "8,79"
    assert pct(0.966) == "96,6 %"
