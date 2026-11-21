import math

from cascadasen.domain.geo import haversine_km, simplify, utm_to_lonlat
from cascadasen.domain.naming import bay_stripped, is_tap_name, line_ends, norm, parse_kv
from cascadasen.domain.unify import max_line_km, plant_key


def test_norm_strips_prefix_voltage_and_accents():
    assert norm("S/E Charrúa 500kV") == "CHARRUA"
    assert norm("S/E POLPAICO_220") == "POLPAICO"


def test_line_ends_handles_en_dash_and_suffixes():
    assert line_ends("ANCOA - ALTO JAHUEL 500KV L1") == ["ANCOA", "ALTO JAHUEL"]
    assert line_ends("CUMBRE – NUEVA CARDONES 500KV") == ["CUMBRE", "NUEVA CARDONES"]


def test_parse_kv_and_bay():
    assert parse_kv("BA S/E CENTRAL ALFALFAL 12KV BP1") == 12.0
    assert parse_kv("sin tension") is None
    assert bay_stripped("S/E OSORNO B3") == "S/E OSORNO"
    assert bay_stripped("S/E ALTO JAHUEL J10") == "S/E ALTO JAHUEL"


def test_tap_names():
    assert is_tap_name("S/E TAP OFF LA CRUZ")
    assert is_tap_name("S/E SECCIONADORA LO AGUIRRE")
    assert not is_tap_name("S/E TAPIHUE")


def test_plant_key_removes_tech_prefix_and_units():
    assert plant_key("TER LOS VIENTOS U1") == "LOS VIENTOS"
    assert plant_key("PFV Campos del Sol") == "CAMPOS DEL SOL"


def test_utm_inverse_matches_known_point():
    # S/E Central Alfalfal: IDE gives 389154 E, 6292393 N (19S) and serves -70.193337, -33.502276
    lon, lat = utm_to_lonlat(389154, 6292393, 19)
    assert haversine_km(lon, lat, -70.193337, -33.502276) < 0.01


def test_haversine_and_simplify():
    assert math.isclose(haversine_km(-70, -30, -70, -31), 111.2, abs_tol=0.3)
    line = [(-70.0, -30.0), (-70.0, -30.00001), (-70.0, -30.5), (-70.0, -31.0)]
    assert simplify(line, 50) == [(-70.0, -30.0), (-70.0, -31.0)]


def test_max_line_km_grows_with_voltage():
    assert max_line_km(66) < max_line_km(110) < max_line_km(220) < max_line_km(500)
