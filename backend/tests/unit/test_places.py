"""Places a person names resolve to the substation that serves them (application/places.py, docs/stress.md)."""

from __future__ import annotations

import pytest

from cascadasen.application.grid_stress import prepare_workflow, stress_context
from cascadasen.application.grids import GridError
from cascadasen.application.places import clean, resolve_place
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


@pytest.mark.parametrize(
    ("place", "bus_name"),
    [
        # the bug: matching area names first sent these to S/E ESCONDIDA and to S/E COLLAHUASI, a mine inland
        ("Antofagasta", "S/E ANTOFAGASTA"),
        ("Arica", "S/E ARICA"),
        ("Iquique", "S/E CONDORES"),  # no substation is called Iquique: the one that serves its people
        ("Concepción", "S/E CONCEPCION"),  # two substations of that name: the one without an owner
        ("cerca de Concepción", "S/E CONCEPCION"),
        ("Calama", "S/E CALAMA NUEVA"),
        ("Puerto Montt", "S/E PUERTO MONTT"),
        ("S/E Alto Jahuel", "S/E ALTO JAHUEL"),
        ("B077", "S/E ESCONDIDA"),
    ],
)
def test_a_place_goes_to_its_own_substation(ctx, place, bus_name):
    assert resolve_place(ctx, place)["bus_name"] == bus_name


def test_a_comuna_beats_an_industrial_substation_of_the_same_name(ctx):
    found = resolve_place(ctx, "Puente Alto")  # S/E PUENTE ALTO (CMPC) is a paper mill
    assert "(CMPC)" not in found["bus_name"] and "comuna de Puente Alto" in found["how"]


def test_regions_and_provinces_use_their_most_populous_comuna(ctx):
    assert "Concepción" in resolve_place(ctx, "Biobío")["how"]  # the region before the province
    assert "Temuco" in resolve_place(ctx, "La Araucanía")["how"]
    assert resolve_place(ctx, "Región Metropolitana")["area"] == "A09"
    assert resolve_place(ctx, "A09")["how"].startswith("barra principal del área A09")


def test_places_off_the_sen_and_unknown_places_say_so(ctx):
    for island in ("Isla de Pascua", "Juan Fernández", "Punta Arenas"):
        with pytest.raises(GridError, match="no está conectada al Sistema Eléctrico Nacional"):
            resolve_place(ctx, island)
    with pytest.raises(GridError, match="Quisiste decir antofagasta"):
        resolve_place(ctx, "Antofagsta")
    with pytest.raises(GridError, match="No encuentro el lugar 'Marte'"):
        resolve_place(ctx, "Marte")


def test_clean_drops_what_people_put_before_a_place():
    assert clean("¿Cerca de la comuna de Viña del Mar?") == "vina del mar"
    assert clean("en la región de Los Lagos") == "los lagos"


def test_a_new_plant_is_built_where_its_technology_was_missing(world):
    """`add` used to be spread by the MW the technology already had, so a solar plant at a substation with no
    solar added nothing and still answered matched 0."""
    out = prepare_workflow(
        world, POINT, [{"target": "generation", "places": ["Iquique"], "tech": ["solar"], "add": 80}]
    )
    change = out["changes"][0]
    assert change["matched"] == 1 and change["new_plant"] and not change["synchronous"]
    assert change["gen_delta_mw"] == 80.0 and change["places"][0]["bus"] == "B058"
    assert "new_plant" in {a["id"] for a in out["assumptions"]}
    thermal = prepare_workflow(
        world, POINT, [{"target": "generation", "places": ["Puerto Montt"], "tech": ["termica"], "add": 300}]
    )
    assert thermal["changes"][0]["synchronous"] and thermal["changes"][0]["sync_delta_mw"] == 300.0
    battery = prepare_workflow(
        world, POINT, [{"target": "generation", "places": ["Santiago"], "tech": ["bateria"], "add": 100}]
    )
    assert battery["changes"][0]["new_plant"] and battery["changes"][0]["sync_delta_mw"] == 0.0


def test_a_new_plant_needs_one_kind_of_technology(world):
    with pytest.raises(GridError, match="necesita su tecnología"):
        prepare_workflow(world, POINT, [{"target": "generation", "places": ["Antofagasta"], "add": 50}])
    with pytest.raises(GridError, match="una sola tecnología"):
        prepare_workflow(
            world,
            POINT,
            [{"target": "generation", "places": ["Antofagasta"], "tech": ["solar", "hidro"], "add": 50}],
        )
    with pytest.raises(GridError, match=r"changes\[0\]: No encuentro el lugar"):
        prepare_workflow(world, POINT, [{"target": "demand", "places": ["Marte"], "add": 50}])


def test_the_places_route_answers_like_a_change_would():
    from fastapi.testclient import TestClient

    from cascadasen.api.app import create_app
    from cascadasen.infrastructure.settings import Settings

    client = TestClient(create_app(settings=Settings(data_dir=REPO_ROOT / "data")))
    found = client.get("/api/v1/grids/places", params={"q": "Iquique"})
    assert found.status_code == 200 and found.json()["bus"] == "B058"
    assert client.get("/api/v1/grids/places", params={"q": "Isla de Pascua"}).status_code == 404
    assert client.get("/api/v1/grids/places", params={"q": ""}).status_code == 422
