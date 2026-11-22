"""A line found by the name a person gives it (application/line_lookup.py, docs/stress.md section 3)."""

from __future__ import annotations

import pytest

from cascadasen.application.grid_stress import stress_context
from cascadasen.application.grids import GridError
from cascadasen.application.line_lookup import MAX_MATCHES, find_lines
from cascadasen.application.places import bus_key
from cascadasen.application.theater_world import default_world
from cascadasen.infrastructure.settings import REPO_ROOT

PROCESSED = REPO_ROOT / "data/processed"
pytestmark = pytest.mark.skipif(not (PROCESSED / "grid_snapshot.json").exists(), reason="no processed data")
POINT = "nov2026-1300"


@pytest.fixture(scope="module")
def world():
    return default_world(str(PROCESSED))


@pytest.fixture(scope="module")
def ctx(world):
    return stress_context(world, POINT)


def ids(found):
    return [ln["id"] for ln in found["lines"]]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        # the request that ran the assistant out of steps on production (25F corridor)
        ("Nueva Maitencillo – Nueva Pan de Azúcar", ["R239"]),
        ("la línea Nueva Maitencillo - Nueva Pan de Azucar (500 kV)", ["R239"]),
        ("Nueva Pan de Azúcar — Nueva Maitencillo", ["R239"]),  # either order
        ("entre Ancoa y Alto Jahuel", ["R006"]),  # Apagón 2011
        ("S/E Ancoa a S/E Alto Jahuel", ["R006"]),
        ("Maitencillo – Pan de Azúcar", ["R216"]),  # the exact names: the old 110 kV line, not the new one
        ("R239", ["R239"]),
        ("Ancoa 500 kV", ["R006", "R026"]),  # one end and a voltage
    ],
)
def test_a_line_is_found_by_its_end_substations(ctx, name, expected):
    assert ids(find_lines(ctx, name)) == expected


def test_every_line_is_found_by_the_names_of_its_ends(ctx):
    names = ctx.names
    for ln in ctx.net.buses.lines:
        for text in (
            f"{bus_key(names[ln.a])} – {bus_key(names[ln.b])}",
            f"entre {names[ln.b]} y {names[ln.a]}",
        ):
            assert ln.id in ids(find_lines(ctx, text)), text


def test_the_answer_is_in_id_order_never_a_ranking(ctx):
    """docs/cyber.md section 8: a lookup by name lists what matches in id order, with no criticality field."""
    found = find_lines(ctx, "Ancoa")
    assert ids(found) == sorted(ids(found)) and found["matched"] == len(found["lines"])
    assert set(found["lines"][0]) == {"id", "name", "kv", "a", "b", "capacity_mw"}
    big = max(range(len(ctx.names)), key=lambda i: sum(i in (ln.a, ln.b) for ln in ctx.net.buses.lines))
    crowded = find_lines(ctx, bus_key(ctx.names[big]))
    assert len(crowded["lines"]) <= MAX_MATCHES


def test_unknown_names_and_missing_lines_say_so(ctx):
    with pytest.raises(GridError, match=r"(?i)No encuentro la subestación 'marte'") as exc:
        find_lines(ctx, "Marte – Ancoa")
    assert exc.value.kind == "not_found"
    with pytest.raises(GridError, match="No hay una línea directa"):
        find_lines(ctx, "Arica – Puerto Montt")
    with pytest.raises(GridError, match="No existe la línea R999"):
        find_lines(ctx, "R999")
    with pytest.raises(GridError) as empty:
        find_lines(ctx, "la línea ")
    assert empty.value.kind == "invalid"


def test_the_lines_route_over_http():
    from fastapi.testclient import TestClient

    from cascadasen.api.app import create_app
    from cascadasen.infrastructure.settings import Settings

    client = TestClient(create_app(settings=Settings(data_dir=REPO_ROOT / "data")))
    found = client.get("/api/v1/grids/lines", params={"q": "Nueva Maitencillo – Nueva Pan de Azúcar"})
    assert found.status_code == 200 and ids(found.json()) == ["R239"]
    assert client.get("/api/v1/grids/lines", params={"q": "Marte – Ancoa"}).status_code == 404
    assert client.get("/api/v1/grids/lines", params={"q": ""}).status_code == 422
