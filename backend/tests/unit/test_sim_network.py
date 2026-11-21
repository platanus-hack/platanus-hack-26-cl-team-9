"""Reduced network: parameter provenance, area assignment, corridors and target resolution."""

import pytest

from cascadasen.domain.simulation.network import UnknownTargetError
from cascadasen.domain.simulation.params import ParameterError, check_provenance, load_params


@pytest.mark.parametrize("name", ["network", "physics", "operating_points", "defenses"])
def test_parameter_files_load_with_provenance(name):
    assert load_params(name)


def test_bare_number_is_rejected():
    with pytest.raises(ParameterError, match="bare number"):
        check_provenance({"reserve": 0.04}, "x.yaml")
    with pytest.raises(ParameterError, match="without source"):
        check_provenance({"reserve": {"value": 0.04}}, "x.yaml")
    check_provenance({"reserve": {"value": 0.04, "is_assumption": True}}, "x.yaml")
    check_provenance({"reserve": {"value": 0.04, "source": "[4]"}}, "x.yaml")


def test_areas_and_corridors(toy_network):
    net = toy_network
    assert net.order == ["T1", "T2", "T3"]
    assert set(net.areas["T2"].aggregates) == {"SE102", "SE104"}
    assert net.areas["T1"].installed_mw == {"termica": 300.0}
    assert set(net.corridors) == {"T1-T2/500", "T2-T3/220"}
    c500 = net.corridors["T1-T2/500"]
    assert not c500.is_assumption and c500.capacity_mw == 2000.0  # PyPSA-CL branch
    assert net.corridors["T2-T3/220"].is_assumption  # typical values
    assert net.areas["T2"].main_node == "SE102"  # 500 kV beats 110 kV


def test_resolve_targets(toy_network):
    net = toy_network
    assert net.resolve("T2").kind == "area"
    node = net.resolve("SE104")
    assert (node.kind, node.area) == ("node", "T2")
    line = net.corridors["T2-T3/220"].members[0]
    assert net.resolve(line).corridor == "T2-T3/220"
    with pytest.raises(UnknownTargetError):
        net.resolve("NOPE")


def test_partial_corridor_outage(toy_network):
    c = toy_network.corridors["T1-T2/500"]
    assert c.effective(frozenset()) == (c.x_pu, c.capacity_mw)
    assert c.effective(frozenset(c.members)) is None
