from cascadasen.domain.regional import (
    RegionalBundle,
    RegionalLine,
    RegionalPlant,
    RegionalSubstation,
    normalise,
    parse_kv_levels,
    simplify_line,
    tech_from_text,
)
from cascadasen.domain.regional_reduction import feature_collections, manifest_entry, reduce_bundle
from cascadasen.infrastructure.sources.regional.energia_argentina import (
    EnergiaArgentinaSource,
    parse_geometry,
)
from cascadasen.infrastructure.sources.regional.epe_brasil import EpeBrasilSource
from cascadasen.infrastructure.sources.regional.osinergmin_peru import OsinergminPeruSource, _mw
from cascadasen.infrastructure.sources.regional.osm_overpass import OsmOverpassSource, parse_mw


def test_parse_kv_levels_handles_every_source_format():
    assert parse_kv_levels(220) == [220.0]
    assert parse_kv_levels("220,5") == [220.5]
    assert parse_kv_levels("500 kV") == [500.0]
    assert parse_kv_levels("500000;220000") == [500.0, 220.0]  # OSM stores volts
    assert parse_kv_levels("") == []
    assert parse_kv_levels(None) == []
    assert parse_kv_levels("sin dato") == []


def test_tech_from_text_covers_spanish_portuguese_and_osm():
    assert tech_from_text("Energía Solar Fotovoltaica") == "solar"
    assert tech_from_text("wind") == "eolica"
    assert tech_from_text("Hidroeléctrica") == "hidro"
    assert tech_from_text("biomass") == "bioenergia"
    assert tech_from_text("diesel") == "termica"
    assert tech_from_text("nuclear") == "nuclear"
    assert tech_from_text(None) is None
    assert tech_from_text("xyz") is None


def test_parse_mw_units():
    assert parse_mw("120 MW") == 120
    assert parse_mw("1.5 GW") == 1500
    assert parse_mw("500 kW") == 0.5
    assert parse_mw("30") == 30
    assert parse_mw("lots") is None


def test_peru_power_in_kw_is_read_as_mw():
    assert _mw(98316) == 98.316
    assert _mw(470.35) == 470.35
    assert _mw(None) is None


def test_simplify_line_drops_collinear_points_and_keeps_ends():
    line = [(-70.0, -33.0), (-70.0, -33.5), (-70.0, -34.0), (-69.0, -34.0)]
    out = simplify_line(line)
    assert out[0] == (-70.0, -33.0) and out[-1] == (-69.0, -34.0)
    assert (-70.0, -33.5) not in out


def _bundle() -> RegionalBundle:
    b = RegionalBundle("XXX", "Pais")
    b.lines += [
        RegionalLine("1", "ok", 220.0, [(-60.0, -10.0), (-60.5, -10.5)], "s"),
        RegionalLine("2", "low", 33.0, [(-60.0, -10.0), (-60.5, -10.5)], "s"),
        RegionalLine("3", "novolt", None, [(-60.0, -10.0), (-60.5, -10.5)], "s"),
        RegionalLine("4", "far", 500.0, [(10.0, 10.0), (11.0, 11.0)], "s"),
    ]
    b.substations += [
        RegionalSubstation("1", "A", 220.0, -60.0, -10.0, "s"),
        RegionalSubstation("2", "A", 220.0, -60.0001, -10.0001, "s"),  # duplicate by name and place
        RegionalSubstation("3", "B", 11.0, -61.0, -10.0, "s"),
    ]
    b.plants += [
        RegionalPlant("1", "P", "solar", 10.0, -60.0, -10.0, "s"),
        RegionalPlant("2", "Q", "solar", 0.0, -60.0, -10.0, "s"),
        RegionalPlant("3", "R", "solar", 5.0, -60.0, -10.0, "s", operating=False),
    ]
    return b


def test_normalise_filters_and_counts():
    out = normalise(_bundle())
    assert [ln.record for ln in out.lines] == ["1"]
    assert out.lines[0].length_km and out.lines[0].length_km > 50  # filled from geometry
    assert [s.record for s in out.substations] == ["1"]
    assert [p.record for p in out.plants] == ["1"]
    assert any("sin tensión" in w for w in out.warnings)
    assert any("menos de 66 kV" in w for w in out.warnings)


def _reduced():
    """Two substations 1 km apart (one bus), a 220 kV double line cut in two OSM ways, a parallel line, a stub."""
    b = RegionalBundle("XXX", "Pais")
    b.substations += [
        RegionalSubstation("a1", "A", 220.0, -60.00, -10.0, "s"),
        RegionalSubstation("a2", "A bis", 110.0, -60.00, -10.01, "s"),  # 1 km away: same bus
        RegionalSubstation("b", "B", 220.0, -61.0, -10.0, "s"),
        RegionalSubstation("c", "C", 220.0, -62.0, -10.0, "s"),
        RegionalSubstation("lonely", "Lonely", 220.0, -50.0, -20.0, "s"),
    ]
    mid = (-60.5, -10.0)
    b.lines += [
        RegionalLine("w1", "", 220.0, [(-60.0, -10.0), mid], "s"),  # A -> free point
        RegionalLine("w2", "", 220.0, [mid, (-61.0, -10.0)], "s"),  # free point -> B, chained with w1
        RegionalLine("p", "", 220.0, [(-60.0, -10.0), (-61.0, -10.0)], "s", circuits=1),  # parallel to A-B
        RegionalLine("bc", "", 220.0, [(-61.0, -10.0), (-62.0, -10.0)], "s"),
        RegionalLine("stub", "", 220.0, [(-62.0, -10.0), (-62.0, -12.0)], "s"),  # ends nowhere
        RegionalLine("loop", "", 220.0, [(-60.0, -10.0), (-60.0, -10.005)], "s"),  # inside one substation
    ]
    b.plants += [
        RegionalPlant("1", "P1", "solar", 30.0, -61.0, -10.0, "s"),
        RegionalPlant("2", "P2", "hidro", 50.0, -61.01, -10.0, "s"),
        RegionalPlant("3", "Far", "solar", 9.0, -40.0, -30.0, "s"),
    ]
    return reduce_bundle(b)


def test_reduction_merges_substations_chains_ways_and_folds_parallels():
    red = _reduced()
    names = {bus.name for bus in red.buses}
    assert {"A", "B", "C"} == names  # "A bis" merged into A, "Lonely" has no line
    assert len(red.links) == 2  # A-B (w1+w2 chained, plus the parallel folded) and B-C; stub and loop gone
    ab = next(ln for ln in red.links if ln.merged >= 3)
    assert ab.circuits == 2 and ab.kv == 220.0
    assert any("misma subestación" in w for w in red.warnings)


def test_reduction_adds_plants_per_bus_and_drops_far_ones():
    red = _reduced()
    assert len(red.generation) == 1
    g = red.generation[0]
    assert g.mw == 80.0 and g.count == 2 and g.tech == "hidro"
    assert any("a más de" in w for w in red.warnings)


def test_reduced_feature_collections_and_manifest():
    red = _reduced()
    cols = feature_collections(red)
    line = cols["lines"]["features"][0]
    assert line["geometry"]["type"] == "LineString" and len(line["geometry"]["coordinates"]) == 2
    bus_ids = {f["properties"]["id"] for f in cols["substations"]["features"]}
    assert {line["properties"]["a"], line["properties"]["b"]} <= bus_ids
    assert cols["plants"]["features"][0]["properties"]["bus"] in bus_ids
    for layer in cols.values():
        for f in layer["features"]:
            assert f["properties"]["country"] == "XXX" and f["properties"]["source"]
    entry = manifest_entry(red)
    assert entry["counts"] == {"lines": 2, "substations": 3, "plants": 1}
    assert entry["raw_counts"]["lines"] == 6 and entry["plant_count"] == 2


class _FakeHttp:
    """Serves canned payloads by cache name; no network."""

    def __init__(self, payloads):
        self.payloads = payloads

    def cached(self, name):
        return None

    def get_json(self, url, cache_name, refresh=False, params=None):
        return self.payloads[cache_name.rsplit("/", 1)[-1].split(".")[0]]

    def get_bytes(self, url, cache_name, refresh=False, headers=None):
        return self.payloads[cache_name.rsplit("/", 1)[-1].split(".")[0]]


def test_osm_adapter_reads_lines_substations_and_plants():
    payloads = {
        "osm_lines": {
            "elements": [
                {
                    "type": "way",
                    "id": 7,
                    "tags": {"power": "line", "voltage": "230000", "circuits": "2"},
                    "geometry": [{"lat": -17.0, "lon": -65.0}, {"lat": -17.5, "lon": -65.5}],
                }
            ]
        },
        "osm_substations": {
            "elements": [
                {
                    "type": "node",
                    "id": 1,
                    "lat": -17.0,
                    "lon": -65.0,
                    "tags": {"voltage": "230000", "name": "S1"},
                }
            ]
        },
        "osm_plants": {
            "elements": [
                {
                    "type": "way",
                    "id": 2,
                    "center": {"lat": -17.2, "lon": -65.2},
                    "tags": {"name": "Hidro", "plant:source": "hydro", "plant:output:electricity": "90 MW"},
                }
            ]
        },
    }
    bundle = OsmOverpassSource(_FakeHttp(payloads), "BOL", "Bolivia", "BO").fetch()
    assert bundle.lines[0].kv == 230.0 and bundle.lines[0].circuits == 2
    assert bundle.substations[0].kv == 230.0
    assert bundle.plants[0].tech == "hidro" and bundle.plants[0].mw == 90
    assert bundle.sources[0].license == "ODbL 1.0"


def test_parse_geometry_geojson_and_wkt():
    assert parse_geometry('{"type":"LineString","coordinates":[[-65,-30],[-64,-31]]}') == [
        [(-65.0, -30.0), (-64.0, -31.0)]
    ]
    assert parse_geometry("LINESTRING (-65 -30, -64 -31)") == [[(-65.0, -30.0), (-64.0, -31.0)]]
    assert parse_geometry("MULTILINESTRING ((-65 -30, -64 -31),(-63 -30, -62 -31))") == [
        [(-65.0, -30.0), (-64.0, -31.0)],
        [(-63.0, -30.0), (-62.0, -31.0)],
    ]
    assert parse_geometry("POINT (-65 -30)") == [[(-65.0, -30.0)]]
    assert parse_geometry("") == []


def test_argentina_adapter_detects_columns():
    lines = 'gid,nombre,tension,geom\n1,Linea A,500 kV,"LINESTRING (-65 -30, -64 -31)"\n'
    subs = "gid,nombre,tension,longitud,latitud\n1,Est A,500,-65,-30\n"
    plants = "gid,nombre,tecnologia,potencia_instalada,longitud,latitud\n1,Central A,Hidráulica,120,-65,-30\n"
    payloads = {"lines": lines.encode(), "substations": subs.encode(), "plants": plants.encode()}
    bundle = EnergiaArgentinaSource(_FakeHttp(payloads)).fetch()
    assert bundle.lines[0].kv == 500.0 and len(bundle.lines[0].coords) == 2
    assert bundle.substations[0].lon == -65.0
    assert bundle.plants[0].mw == 120.0 and bundle.plants[0].tech == "hidro"


LINE = {"type": "LineString", "coordinates": [[-50.0, -10.0], [-51.0, -11.0]]}
POINT = {"type": "Point", "coordinates": [-50.0, -10.0]}


def test_epe_adapter_reads_layers_and_converts_kw(monkeypatch):
    layers = {
        23: [
            {
                "properties": {"OBJECTID": 1, "Nome": "LT A", "Tensao": 500, "Extensao": 100.0},
                "geometry": LINE,
            }
        ],
        22: [{"properties": {"OBJECTID": 2, "Nome": "SE A", "Tensao": 500}, "geometry": POINT}],
        16: [{"properties": {"OBJECTID": 3, "NOME": "UHE A", "potencia": 14000000}, "geometry": POINT}],
    }
    monkeypatch.setattr(
        "cascadasen.infrastructure.sources.regional.epe_brasil.query_layer",
        lambda http, url, cache, refresh=False, **kw: layers.get(int(url.rsplit("/", 1)[1]), []),
    )
    bundle = EpeBrasilSource(None, "http://x").fetch()
    assert bundle.lines[0].kv == 500.0 and bundle.lines[0].length_km == 100.0
    assert bundle.substations[0].name == "SE A"
    assert bundle.plants[0].tech == "hidro" and bundle.plants[0].mw == 14000.0


def test_peru_adapter_reads_layers_by_voltage(monkeypatch):
    layers = {
        31: [
            {
                "properties": {
                    "OBJECTID": 1,
                    "NOMBRE": "L-2001",
                    "TENSION_NOM": 220,
                    "LONGITUD": 80,
                    "NRO_TERNAS": 2,
                },
                "geometry": LINE,
            }
        ],
        25: [{"properties": {"OBJECTID": 2, "NOMBRE": "SET A", "TENSION_NOM": 220}, "geometry": POINT}],
        20: [
            {
                "properties": {"OBJECTID": 3, "NOMBRE": "Solar A", "POT_INST": 40.0, "FUENTE_ENER": "Solar"},
                "geometry": POINT,
            }
        ],
    }
    monkeypatch.setattr(
        "cascadasen.infrastructure.sources.regional.osinergmin_peru.query_layer",
        lambda http, url, cache, refresh=False, **kw: layers.get(int(url.rsplit("/", 1)[1]), []),
    )
    bundle = OsinergminPeruSource(None, "http://x").fetch()
    assert bundle.lines[0].kv == 220.0 and bundle.lines[0].circuits == 2
    assert bundle.substations[0].kv == 220.0
    assert bundle.plants[0].tech == "solar" and bundle.plants[0].mw == 40.0
