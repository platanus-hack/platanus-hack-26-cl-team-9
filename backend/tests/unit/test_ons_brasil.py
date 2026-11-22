"""Brazil flow network from ONS (domain/regional_network.py, infrastructure/sources/regional/ons_brasil.py)."""

import json
import math

import pytest

from cascadasen.application.build_regional import BuildRegionalGrid
from cascadasen.domain.cascade.network import X_MIN_PU
from cascadasen.domain.regional import (
    RegionalBundle,
    RegionalLine,
    RegionalPlant,
    RegionalSource,
    RegionalSubstation,
)
from cascadasen.domain.regional_network import (
    Circuit,
    OnsBusbar,
    OnsDataset,
    OnsLine,
    _capacity_mw,
    _fold_parallel_lines,
    _normalise_substation_name,
    _ohm,
    _to_per_unit,
    build_flow_network,
    deduction_error,
    flow_manifest_entry,
    network_document,
)
from cascadasen.domain.regional_reduction import ReducedRegional, RegionalBus, RegionalLink
from cascadasen.infrastructure.sources.regional.ons_brasil import OnsBrasilSource, parse_busbars, parse_lines


def test_per_unit_matches_a_hand_calculation():
    # LT 230 kV Cruzeiro do Sul - Feijó: 280 km, val_reatancia 23.846 (percent on 100 MVA)
    x = _to_per_unit(23.846)
    assert x == pytest.approx(0.23846)
    assert _ohm(x, 230.0) == pytest.approx(0.23846 * 230**2 / 100)  # 126.15 ohm
    assert _ohm(x, 230.0) / 280 == pytest.approx(0.4505, abs=1e-4)  # textbook 230 kV ohm/km
    assert _to_per_unit(None) is None


def test_capacity_in_mw_from_amperes():
    assert _capacity_mw(230.0, 780.0) == pytest.approx(math.sqrt(3) * 230 * 780 / 1000)  # 310.7 MW
    assert _capacity_mw(230.0, 780.0) == pytest.approx(310.7, abs=0.1)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SE Araraquara 2", "ARARAQUARA 2"),
        ("ARARAQUARA 2", "ARARAQUARA 2"),
        ("JUAZEIRO III", "JUAZEIRO 3"),
        ("SE Juazeiro 3", "JUAZEIRO 3"),
        ("PORTO PECEM II", "PORTO PECEM 2"),
        ("SE Foz do Iguaçu", "FOZ DO IGUACU"),
        ("S/E Feijó", "FEIJO"),
        ("F.IGUACU 50HZ", "F IGUACU 50HZ"),
    ],
)
def test_normalise_substation_name(raw, expected):
    assert _normalise_substation_name(raw) == expected


def _circuit(record, x_pu, cap, r_pu=0.01, b_pu=0.1, a="A", b="B", kv=500.0):
    return Circuit(record, a, b, kv, 100.0, r_pu, x_pu, b_pu, None, cap, ())


def test_fold_parallel_lines_like_chile():
    (line,) = _fold_parallel_lines([_circuit("c1", 0.02, 1000.0), _circuit("c2", 0.02, 1500.0)], "XX-L")
    assert line.circuits == 2 and line.branches == ["c1", "c2"]
    assert line.x_pu == pytest.approx(0.01)  # reactances in parallel
    assert line.r_pu == pytest.approx(0.005)
    assert line.b_pu == pytest.approx(0.2)  # susceptances add up
    assert line.capacity_mw == 2500.0  # capacities add up


def test_fold_parallel_lines_floors_tiny_reactance():
    (line,) = _fold_parallel_lines([_circuit("c1", 4e-4, 100.0), _circuit("c2", 4e-4, 100.0)], "XX-L")
    assert line.x_pu == X_MIN_PU


def _line(record, f, t, kv=230.0, x=10.0, amps=780.0, kind="ac", **kw):
    base = dict(
        record=record,
        name=f"LT {record}",
        kind=kind,
        kv=kv,
        length_km=100.0,
        r_pct=1.0,
        x_pct=x,
        shunt_mvar=20.0,
        amps=amps,
        bus_from=f,
        bus_to=t,
        sub_from=f"S{f}",
        sub_to=f"S{t}",
        entered="2020-01-01",
    )
    return OnsLine(**(base | kw))


def _dataset():
    busbars = [
        OnsBusbar("1", "A", "ALFA", 230.0, -20.0, -45.0),
        OnsBusbar("2", "A", "ALFA", 500.0, -20.0, -45.0),
        OnsBusbar("3", "B", "BETA", 500.0, -21.0, -45.0),
        OnsBusbar("4", "C", "GAMA", 230.0, -20.0, -46.0),
        OnsBusbar("5", "D", "DELTA III", 230.0, None, None),  # coordinates only from EPE by name
        OnsBusbar("6", "E", "EPSILON", 230.0, None, None),  # no coordinates anywhere
    ]
    lines = [
        _line("AB1", "2", "3", kv=500.0, x=2.0, amps=2000.0),
        _line("AB2", "2", "3", kv=500.0, x=2.0, amps=None),  # no amperes: typical capacity
        _line("AC1", "1", "4", x=23.846, amps=780.0, length_km=280.0),
        _line("CD1", "4", "5"),
        _line("CE1", "4", "6"),
        _line("OLD", "1", "4", deactivated="2015-01-01"),
        _line("NEW", "1", "4", entered="2030-01-01"),
        _line("DC1", "2", "3", kv=600.0, x=0.0, amps=1000.0, kind="dc"),
        _line("RAM", "4", "", kind="ramal", sub_to=""),
        _line("URU", "4", "99", sub_to="RIVERA"),
    ]
    source = RegionalSource("ons", "ONS", "ONS", "u", "CC BY", "ONS Dados Abertos", ("lines",))
    return OnsDataset(lines, busbars, [source])


EPE_SUBS = [RegionalSubstation("9", "SE Delta 3", 230.0, -46.0, -19.0, "EPE capa 22", [230.0])]
EPE_PLANTS = [
    RegionalPlant("p1", "UHE Alfa", "hidro", 300.0, -45.01, -20.0, "EPE capa 16"),
    RegionalPlant("p2", "Lejos", "solar", 50.0, -30.0, -5.0, "EPE capa 15"),
]


def _net():
    return build_flow_network(_dataset(), EPE_SUBS, EPE_PLANTS, "2026-11-21", "BRA")


def test_build_flow_network_folds_substations_and_filters_rows():
    net = _net()
    assert [b.id for b in net.buses] == ["BRA-A", "BRA-B", "BRA-C", "BRA-D"]
    alfa = net.buses[0]
    assert alfa.kv == 500.0 and alfa.kv_levels == [500.0, 230.0] and alfa.busbars == ["1", "2"]
    lines = {(ln.a, ln.b): ln for ln in net.lines}
    assert set(lines) == {("BRA-A", "BRA-B"), ("BRA-A", "BRA-C"), ("BRA-C", "BRA-D")}
    ab = lines[("BRA-A", "BRA-B")]
    assert ab.circuits == 2 and ab.x_pu == pytest.approx(0.01)
    assert ab.capacity_mw == pytest.approx(2 * _capacity_mw(500.0, 2000.0), abs=0.1)
    assert ab.assumed_fields == ["capacity_mw"] and ab.capacity_a == [2000.0, None]
    assert net.stats["excluded"] == {
        "deactivated": 1,
        "future": 1,
        "ramal": 1,
        "foreign_end": 1,
        "no_coordinates": 1,
    }
    assert [ln.branches for ln in net.dc_links] == [["DC1"]]


def test_missing_coordinates_and_foreign_ends_are_warned_with_name_and_kv():
    net = _net()
    delta = next(b for b in net.buses if b.id == "BRA-D")
    assert (
        delta.coord_source == "epe_exact" and delta.is_assumption and (delta.lon, delta.lat) == (-46.0, -19.0)
    )
    assert any("EPSILON 230 kV" in w for w in net.warnings)
    assert any("RIVERA 230 kV" in w for w in net.warnings)
    assert any("ramales" in w for w in net.warnings)
    coords = net.stats["coordinates"]
    assert coords["from_ons"] == 3 and coords["from_epe_exact_name"] == 1 and coords["missing"] == 1


def test_plants_attach_to_the_nearest_bus_and_far_ones_are_counted():
    net = _net()
    assert [(p.bus, p.mw) for p in net.plants] == [("BRA-A", 300.0)]
    assert any("50 MW" in w for w in net.warnings)


def test_network_document_carries_provenance_on_every_element():
    doc = network_document(_net(), "2026-11-21T00:00:00+00:00")
    assert doc["country"] == "BRA" and doc["base_mva"] == 100.0
    for key in ("buses", "lines", "dc_links", "plants"):
        for item in doc[key]:
            assert item["country"] == "BRA" and item["source"] and isinstance(item["is_assumption"], bool)
    ab = next(ln for ln in doc["lines"] if ln["a"] == "BRA-A" and ln["b"] == "BRA-B")
    assert ab["is_assumption"] and "capacity_mw" in ab["source"]
    assert doc["dc_links"][0]["dc"] is True and "x_pu" not in doc["dc_links"][0]
    entry = flow_manifest_entry(_net(), "t")
    assert entry["assumed"]["capacity_mw"] == 1
    assert entry["counts"]["buses"] == 4 and entry["counts"]["dc_links"] == 1


def test_deduction_error_compares_parameters_and_topology():
    net = _net()
    drawn = ReducedRegional("BRA", "Brasil", [])
    drawn.buses = [
        RegionalBus("D1", "Alfa", 500.0, [500.0], -45.0, -20.0, "substation", [], []),
        RegionalBus("D2", "Beta", 500.0, [500.0], -45.0, -21.0, "substation", [], []),
        RegionalBus("D3", "Gama", 230.0, [230.0], -46.0, -20.0, "substation", [], []),
    ]
    drawn.links = [
        RegionalLink("R1", "D1", "D2", 500.0, 1, 100.0, [], []),  # true corridor
        RegionalLink("R2", "D2", "D3", 230.0, 1, 100.0, [], []),  # false: ONS has no B-C line
    ]
    err = deduction_error(net, drawn, {500.0: (0.2, 0.4), 220.0: (0.4, 0.6)}, {500.0: 2000.0, 220.0: 400.0})
    assert err["topology"]["precision"] == 0.5
    assert err["topology"]["recall"] == 0.5  # A-C exists in ONS, not in the drawn layer
    # AC1: real 0.23846 pu = 126.15 ohm, deduced 0.5 ohm/km * 280 km = 140 ohm -> +0.110
    # CD1: real 0.1 pu = 52.9 ohm, deduced 50 ohm -> -0.055. CE1 is gone (an end without coordinates).
    assert err["x"]["230"] == {"n": 2, "median_abs": 0.082, "p90_abs": 0.104, "median_bias": 0.028}
    # AB1: real sqrt(3) * 500 kV * 2000 A = 1732 MW, deduced 2000 MW -> +0.155; AB2 has no real value
    assert err["capacity"]["500"] == {"n": 1, "median_abs": 0.155, "p90_abs": 0.155, "median_bias": 0.155}


LINES_CSV = (
    "nom_subestacao_de;nom_subestacao_para;val_niveltensao_kv;nom_tipolinha;nom_linhadetransmissao;"
    "cod_equipamento;dat_entradaoperacao;dat_desativacao;val_comprimento;val_resistencia;val_reatancia;"
    "val_shunt;val_capacoperlongasemlimit;val_capacoperlongacomlimit;num_barra_de;num_barra_para\n"
    "CRUZEIRO SUL;FEIJO               ;230.0;LINHA DE TRANSMISSÃO;LT  230 kV CRUZEIRO SUL / FEIJO C 1;"
    "ACCS--2FJ--1        ;2024-12-16;;280.0;3.791;23.846;44.8;780.0;700.0;6990;6980\n"
    "XINGU;ESTREITO;800.0;LINHA DC;CC 800 kV XINGU / ESTREITO C 1;X1;2019-01-01;;2084.0;1.0;150.0;;"
    "2625.0;2625.0;95473;93385\n"
    "A;B;230.0;LINHA DE TRANSMISSÃO;LT A / B;OLD1;2000-01-01;2013-06-09;10.0;;;;;;1;2\n"
    ";;;LINHA DE TRANSMISSÃO;sin tension;Z;;;;;;;;;;\n"
).encode()
SUBS_CSV = (
    b"id_subestacao;nom_subestacao;val_niveltensao;num_barra;val_latitude;val_longitude\n"
    b"ACFJO;FEIJO;230.0;6980;-8.16;-70.35\n"
    b"BAUSI;USIBA;230.0;8046;;\n"
    b"BAD;MALA;230.0;7;999;-70\n"
)


def test_adapter_parses_the_ons_csv():
    lines = parse_lines(LINES_CSV)
    assert [ln.record for ln in lines] == ["ACCS--2FJ--1", "X1", "OLD1"]  # the row with no voltage is dropped
    first = lines[0]
    assert first.sub_to == "FEIJO" and first.bus_from == "6990" and first.kind == "ac"
    assert first.amps == 700.0  # long duration WITH limiting factor
    assert (first.r_pct, first.x_pct, first.shunt_mvar, first.length_km) == (3.791, 23.846, 44.8, 280.0)
    assert lines[1].kind == "dc" and lines[2].deactivated == "2013-06-09" and lines[2].x_pct is None
    bars = parse_busbars(SUBS_CSV)
    assert [(b.number, b.substation, b.lat) for b in bars] == [
        ("6980", "ACFJO", -8.16),
        ("8046", "BAUSI", None),
        ("7", "BAD", None),  # out-of-range coordinates are treated as missing
    ]


class _FakeHttp:
    def __init__(self, payloads):
        self.payloads = payloads

    def get_bytes(self, url, cache_name, refresh=False, headers=None):
        return self.payloads[cache_name.rsplit("/", 1)[-1]]


def test_adapter_fetch_uses_the_cache_and_states_the_licence():
    http = _FakeHttp({"ons_linha_transmissao.csv": LINES_CSV, "ons_subestacao.csv": SUBS_CSV})
    ds = OnsBrasilSource(http, "lines-url", "subs-url").fetch()
    assert len(ds.lines) == 3 and len(ds.busbars) == 3
    assert {s.id for s in ds.sources} == {"ons_linha_transmissao", "ons_subestacao"}
    assert all("CC BY" in s.license for s in ds.sources)


class _FixedSource:
    country = "XXX"

    def fetch(self, refresh=False):
        b = RegionalBundle("XXX", "Pais")
        b.substations += [
            RegionalSubstation("a", "A", 220.0, -60.0, -10.0, "s"),
            RegionalSubstation("b", "B", 220.0, -61.0, -10.0, "s"),
            RegionalSubstation("c", "C", 220.0, -62.0, -10.0, "s"),
        ]
        b.lines += [
            RegionalLine("1", "AB", 220.0, [(-60.0, -10.0), (-61.0, -10.0)], "s"),
            RegionalLine("2", "BC", 220.0, [(-61.0, -10.0), (-62.0, -10.0)], "s"),
        ]
        return b


def test_rebuilding_the_drawn_layer_keeps_the_flow_block(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps(
            {"version": 1, "countries": {"XXX": {"country": "XXX", "flow": {"file": "XXX/network.json"}}}}
        )
    )
    manifest, errors = BuildRegionalGrid({"XXX": _FixedSource()}, tmp_path).execute(["XXX"])
    assert not errors
    assert manifest["countries"]["XXX"]["flow"] == {"file": "XXX/network.json"}
    assert manifest["countries"]["XXX"]["counts"]["lines"] == 2
