"""Shared fixtures: a toy grid small enough to reason about by hand.

    A(500) ---L1--- B(500) ---L2--- C(220)          plants: P1 at A (300 MW), P2 at C (50 MW)
                     |
                     +-- T1 (CEN tramo B-D, no IDE geometry) -- D(110, zonal, feeds comuna 2)

Comuna 1 (pop 1000) sits around C, comuna 2 (pop 500) around D.
"""

from __future__ import annotations

import pytest

from cascadasen.domain.model import (
    RawBranch,
    RawBus,
    RawBusbar,
    RawCensusZone,
    RawComuna,
    RawLine,
    RawPlant,
    RawSubstation,
    SourceBundle,
    SourceInfo,
)
from cascadasen.domain.unify import GridUnifier


def _square(lon: float, lat: float, d: float = 0.2) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [lon - d, lat - d],
                [lon + d, lat - d],
                [lon + d, lat + d],
                [lon - d, lat + d],
                [lon - d, lat - d],
            ]
        ],
    }


@pytest.fixture
def toy_bundle() -> SourceBundle:
    b = SourceBundle()
    b.sources = [SourceInfo("ide_energia", "IDE", "MinEnergia", "https://example", ("x",))]
    subs = [
        ("1", "S/E ALFA", -70.0, -30.0, 500, "NACIONAL", 101, "SE001T0001", "04101"),
        ("2", "S/E BETA", -70.0, -31.0, 500, "NACIONAL", 102, "SE002T0001", "04102"),
        ("3", "S/E GAMMA", -70.0, -32.0, 220, "ZONAL", 103, "SE003T0001", "05101"),
        ("4", "S/E DELTA", -70.5, -31.0, 110, "ZONAL", 104, "SE004T0001", "04103"),
    ]
    for rid, name, lon, lat, kv, seg, cen_id, code, comuna in subs:
        b.substations.append(
            RawSubstation(
                "ide_energia", rid, name, lon, lat, kv, seg, "SEN", "Owner", comuna[:2], comuna, cen_id
            )
        )
        b.cen_substations.append(
            RawSubstation("cen_infotecnica", str(cen_id), name, cen_id=cen_id, cen_code=code)
        )
    b.busbars.append(RawBusbar("cen_infotecnica", "1", 102, "BA S/E BETA 220KV B1", 220.0))
    b.geo_lines = [
        RawLine(
            "ide_energia",
            "11",
            "ALFA - BETA 500KV",
            500,
            "C1",
            "NACIONAL",
            "SEN",
            "T",
            111.0,
            [(-70.0, -30.0), (-70.0, -30.5), (-70.0, -31.0)],
        ),
        RawLine(
            "ide_energia",
            "12",
            "BETA - GAMMA 220KV",
            220,
            "C1",
            "ZONAL",
            "SEN",
            "T",
            111.0,
            [(-70.0, -31.0), (-70.0, -32.0)],
        ),
    ]
    b.cen_sections = [
        RawLine(
            "cen_infotecnica",
            "900",
            "ALFA - BETA 500KV C1",
            500,
            "C1",
            end1="Paño : PA S/E ALFA J1/PA001T0001SE001T0001",
            end2="Paño : PA S/E BETA J1/PA001T0001SE002T0001",
        ),
        RawLine(
            "cen_infotecnica",
            "901",
            "BETA - DELTA 110KV C1",
            110,
            "C1",
            end1="Paño: S/E BETA H3",
            end2="Paño: S/E DELTA H1",
        ),
    ]
    b.plants = [
        RawPlant(
            "ide_energia", "TER1", "ALFA", "termica", 300.0, -70.001, -30.001, "EN OPERACION", True, "SEN"
        ),
        RawPlant(
            "ide_energia", "SOL1", "SOLAR GAMMA", "solar", 50.0, -70.01, -32.01, "OPERATIVA", True, "SEN"
        ),
    ]
    b.buses = [
        RawBus("pypsa_cl", "S/E ALFA_500", 500, -70.0, -30.0),
        RawBus("pypsa_cl", "S/E BETA_500", 500, -70.0, -31.0),
    ]
    b.branches = [
        RawBranch(
            "pypsa_cl",
            "S/E ALFA_500->S/E BETA_500",
            "S/E ALFA_500",
            "S/E BETA_500",
            500,
            2000.0,
            1.0,
            30.0,
            None,
            None,
            2020,
            "Line",
        )
    ]
    b.model_generators = [
        RawPlant(
            "pypsa_cl",
            "G0",
            "TER ALFA U1",
            "coal",
            300.0,
            -70.0005,
            -30.0005,
            connection_bus="S/E ALFA_500",
            inertia_s=4.0,
        )
    ]
    b.comunas = [
        RawComuna(
            "ine",
            "5101",
            "Gamma",
            "05",
            "Valparaíso",
            None,
            1000,
            300,
            320,
            (-70.0, -32.0),
            _square(-70.0, -32.0),
        ),
        RawComuna(
            "ine",
            "4103",
            "Delta",
            "04",
            "Coquimbo",
            None,
            500,
            150,
            160,
            (-70.5, -31.0),
            _square(-70.5, -31.0),
        ),
    ]
    b.census_zones = [
        RawCensusZone("ine", "z1", "5101", 800, -70.0, -32.0, True),
        RawCensusZone("ine", "z2", "4103", 500, -70.5, -31.0, True),
    ]
    return b


@pytest.fixture
def toy_snapshot(toy_bundle):
    return GridUnifier().unify(toy_bundle)


@pytest.fixture
def toy_spec():
    """Three areas over the toy grid: ALFA | BETA + DELTA | GAMMA."""
    from cascadasen.domain.simulation.network import AreaSpec, NetworkSpec

    return NetworkSpec(
        areas=(
            AreaSpec("T1", "Toy norte", "NC", -30.5),
            AreaSpec("T2", "Toy centro", "NC", -31.5),
            AreaSpec("T3", "Toy sur", "CE", None),
        )
    )


@pytest.fixture
def toy_network(toy_snapshot, toy_spec):
    from cascadasen.domain.simulation.network import build_reduced_network

    return build_reduced_network(toy_snapshot, toy_spec)
