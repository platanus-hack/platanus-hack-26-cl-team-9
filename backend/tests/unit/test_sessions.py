"""Session use cases on the toy world: revisions, conditional writes, sandbox cuts and nested runs."""

import pytest

from cascadasen.application.run_experiment import RunCache
from cascadasen.application.sessions import (
    PreconditionFailedError,
    SessionNotFoundError,
    SessionService,
)
from cascadasen.domain.cascade.overlay import OverlayError
from cascadasen.domain.ports import ConflictError
from cascadasen.domain.simulation.grid import Physics
from cascadasen.infrastructure.document_store import MemoryDocumentStore

DC = {"bus": "B002", "mw": 100, "kind": "datacenter", "name": "DC Toy"}
RUN = {"template": "open_field", "seed": 3, "horizon": 8}


@pytest.fixture(scope="module")
def physics():
    return Physics.load()


@pytest.fixture
def service(toy_world, toy_spec, physics):
    return SessionService(toy_world, physics, MemoryDocumentStore(), RunCache(), spec=toy_spec)


def test_edits_bump_the_revision_and_show_in_the_network(service):
    sid = service.create()["session_id"]
    assert service.get(sid)["revision"] == 0 and len(sid) == 22
    out = service.add(sid, "load", DC)
    assert (out["id"], out["revision"]) == ("D001", 1)
    assert out["balance"][0]["is_assumption"] is True
    view = service.network_view(sid)
    assert view["buses"]["B002"]["load_mw"] == 250.0
    assert view["balance"] and view["revision"] == 1
    assert view["loads"][0]["id"] == "D001" and view["loads"][0]["origin"] == "session"
    assert view["baseline"]["load_shed_mw"] == 0
    assert service.get(sid)["last_op"] == {
        "op": "load_added",
        "ids": ["D001"],
        "by": "anon",
        "revision": 1,
        "dataset_revision": 1,
    }


def test_run_activity_does_not_move_the_dataset_revision(service):
    sid = service.create()["session_id"]
    edit = service.add(sid, "load", DC)
    view = service.network_view(sid)
    rid = service.create_run(sid, RUN)["run_id"]
    stepped = service.run_command(sid, rid, "step", 1)
    doc = service.get(sid)
    assert stepped["session_revision"] == doc["revision"] == 3
    assert doc["dataset_revision"] == edit["dataset_revision"] == 1
    again = service.network_view(sid)
    assert again["revision"] == 3 and again["dataset_revision"] == view["dataset_revision"] == 1
    # an editor holding dataset_revision 1 is not refused because of the run
    assert service.add(sid, "load", DC, if_revision=1)["dataset_revision"] == 2
    with pytest.raises(PreconditionFailedError):
        service.add(sid, "load", DC, if_revision=1)


def test_a_lost_run_index_write_does_not_fail_the_step(service, monkeypatch):
    sid = service.create()["session_id"]
    rid = service.create_run(sid, RUN)["run_id"]
    put = service.store.put

    def busy(key, doc, **kw):
        if key == f"sessions/{sid}.json":
            raise ConflictError(key)
        return put(key, doc, **kw)

    monkeypatch.setattr(service.store, "put", busy)
    out = service.run_command(sid, rid, "step", 1)
    assert out["run"]["cycle"] == 1 and out["session_revision"] == 1


def test_a_stale_if_revision_is_rejected(service):
    sid = service.create()["session_id"]
    service.add(sid, "load", DC, if_revision=0)
    with pytest.raises(PreconditionFailedError):
        service.add(sid, "load", DC, if_revision=0)


def test_a_store_conflict_is_retried(service, monkeypatch):
    sid = service.create()["session_id"]
    put, calls = service.store.put, []

    def flaky(key, doc, **kw):
        calls.append(key)
        if len(calls) == 1:
            raise ConflictError(key)
        return put(key, doc, **kw)

    monkeypatch.setattr(service.store, "put", flaky)
    assert service.add(sid, "load", DC)["revision"] == 1
    assert len(calls) == 2


def test_a_run_keeps_the_dataset_it_was_created_with(service):
    sid = service.create()["session_id"]
    rid = service.create_run(sid, RUN)["run_id"]
    service.add(sid, "load", DC)
    run_load = service.runs(sid).get(rid).world.load("nov2026-1300")[1].load.sum()
    view = service.network_view(sid)
    assert run_load == pytest.approx(650.0)
    assert sum(b["load_mw"] for b in view["buses"].values()) == pytest.approx(750.0)
    assert service.get(sid)["runs"][rid]["dataset_revision"] == 0


def test_an_evicted_session_run_is_rebuilt(toy_world, toy_spec, physics):
    service = SessionService(toy_world, physics, MemoryDocumentStore(), RunCache(1), spec=toy_spec)
    sid = service.create()["session_id"]
    service.add(sid, "load", DC)
    a = service.create_run(sid, RUN)["run_id"]
    service.run_command(sid, a, "step", 3)
    head = service.run_command(sid, a, "trace")["head"]
    service.create_run(sid, {**RUN, "seed": 4})  # evicts A
    run = service.run_command(sid, a, "state")["run"]
    assert run["rebuilt"] is True and run["trace_matches"] is True and run["cycle"] == 3
    assert service.run_command(sid, a, "trace")["head"] == head
    assert service.get(sid)["runs"][a]["cycle"] == 3


def test_cut_then_repair_all(service):
    sid = service.create()["session_id"]
    cut = service.cut(sid, ["R1"])
    assert cut["open_lines"] == ["R1"] and cut["timeline"]["failed_elements"] == ["R1"]
    repaired = service.repair(sid, all=True)
    assert repaired["open_lines"] == [] and repaired["timeline"]["failed_elements"] == []
    assert service.state(sid)["revision"] == repaired["revision"] == 2
    assert repaired["dataset_revision"] == 2


def test_delete_removes_the_session(service):
    sid = service.create()["session_id"]
    service.create_run(sid, RUN)
    service.delete(sid)
    with pytest.raises(SessionNotFoundError):
        service.get(sid)
    with pytest.raises(SessionNotFoundError):
        service.get("../../etc/passwd")


def test_an_external_action_runs_in_the_next_cycle(service):
    sid = service.create()["session_id"]
    rid = service.create_run(sid, RUN)["run_id"]
    service.run_command(sid, rid, "inject", "C3_transmission_opening", "T2-T3", None, "intentional")
    service.run_command(sid, rid, "step", 1)
    queued = service.run_command(sid, rid, "action", "restore_element", "T2-T3", "operations", agent="bot")
    assert queued["accepted"] is True
    snap = service.run_command(sid, rid, "step", 1)["snapshots"][0]
    assert any(e["action"] == "restore_element" and e["target"] == "T2-T3" for e in snap["executed"])
    assert service.run_command(sid, rid, "trace")["verified"] is True


SUB = {"name": "SE Nueva", "lat": -31.1, "lon": -71.0, "kv": 220, "connections": [{"to": "B002"}]}


def test_a_substation_is_one_revision_and_survives_further_edits(service):
    sid = service.create()["session_id"]
    out = service.add_substation(sid, SUB)
    assert (out["id"], out["line_ids"], out["revision"]) == ("B006", ["U001"], 1)
    assert service.get(sid)["last_op"]["ids"] == ["B006", "U001"]
    service.add(sid, "load", DC)
    view = service.network_view(sid)
    assert "B006" in view["buses"] and any(ln["id"] == "U001" for ln in view["lines"])


def test_a_failed_substation_changes_nothing(service):
    sid = service.create()["session_id"]
    with pytest.raises(OverlayError):
        service.add_substation(sid, {**SUB, "connections": [{"to": "B002"}, {"to": "B999"}]})
    assert service.get(sid)["revision"] == 0


def test_reset_with_a_scenario_replaces_what_the_session_added(service, toy_world):
    LINE = toy_world.load("nov2026-1300")[0].buses.lines[0].id
    sid = service.create()["session_id"]
    service.add_substation(sid, SUB)
    out = service.reset(sid, scenario={"changes": [], "open_lines": [LINE], "out_buses": ["B004"]})
    assert out["revision"] == 2
    doc = service.get(sid)
    assert doc["overlay"]["buses"] == [] and doc["overlay"]["bus_overrides"]["B004"] == {"in_service": False}
    assert doc["open_lines"] == [LINE]


def test_reset_with_a_scenario_of_another_point_is_refused(service):
    sid = service.create()["session_id"]
    with pytest.raises(OverlayError):
        service.reset(sid, scenario={"point": "feb2025-1500"})
    assert service.get(sid)["revision"] == 0
