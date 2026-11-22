"""Persisted strategic runs: eviction and restart rebuild the run from its record."""

import threading

import pytest

from cascadasen.application.run_experiment import (
    RunCache,
    RunConflictError,
    RunManager,
    RunNotFoundError,
)
from cascadasen.domain.simulation.grid import Physics
from cascadasen.domain.theater.cycle import RunConfig
from cascadasen.infrastructure.document_store import MemoryDocumentStore


@pytest.fixture(scope="module")
def physics():
    return Physics.load()


def _run_a(manager):
    rid = manager.create(RunConfig(template="open_field", seed=3, horizon=8))["run_id"]
    manager.inject(rid, "C3_transmission_opening", "T2-T3", None, "intentional")
    manager.step(rid, 3)
    manager.action(rid, "restore_element", "T2-T3", "operations", agent="bot")  # pending at cycle 3
    return rid


def test_evicted_run_is_rebuilt_with_the_same_trace(toy_world, physics):
    manager = RunManager(toy_world, physics, max_runs=1, store=MemoryDocumentStore())
    a = _run_a(manager)
    head = manager.trace(a)["head"]
    assert manager.summary(a)["rebuilt"] is False
    manager.create(RunConfig(template="open_field", seed=4, horizon=8))  # evicts A
    assert len(manager.cache) == 1
    summary = manager.summary(a)
    assert summary["rebuilt"] is True and summary["trace_matches"] is True and summary["cycle"] == 3
    assert manager.trace(a)["head"] == head
    # the pending action was re-queued: the next step executes it as before
    snap = manager.step(a, 1)["snapshots"][0]
    assert any(e["action"] == "restore_element" and e["target"] == "T2-T3" for e in snap["executed"])


def test_a_restarted_manager_rebuilds_from_the_shared_store(toy_world, physics):
    store = MemoryDocumentStore()
    first = RunManager(toy_world, physics, store=store)
    a = _run_a(first)
    first.step(a, 1)
    head = first.trace(a)["head"]
    second = RunManager(toy_world, physics, store=store)  # a restart or another instance
    assert second.trace(a)["head"] == head
    assert second.summary(a)["trace_matches"] is True and second.summary(a)["cycle"] == 4


def test_concurrent_steps_are_serialised(toy_world, physics):
    manager = RunManager(toy_world, physics, store=MemoryDocumentStore())
    a = _run_a(manager)
    threads = [threading.Thread(target=manager.step, args=(a, 2)) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert manager.summary(a)["cycle"] == 7
    record, _ = manager.store.get(f"runs/{a}.json")
    assert record["cycle"] == 7 and record["trace_head"] == manager.trace(a)["head"]


@pytest.mark.parametrize("run_id", ["../x", "nope", "ABCDEF123456", "0123456789abc"])
def test_bad_ids_are_not_found(toy_world, physics, run_id):
    manager = RunManager(toy_world, physics, store=MemoryDocumentStore())
    with pytest.raises(RunNotFoundError):
        manager.summary(run_id)


def test_a_stale_record_gives_a_conflict(toy_world, physics):
    store, cache = MemoryDocumentStore(), RunCache()
    mine = RunManager(toy_world, physics, store=store, cache=cache)
    a = mine.create(RunConfig(template="open_field", seed=3, horizon=8))["run_id"]
    other = RunManager(toy_world, physics, store=store)  # another instance with its own cache
    other.step(a, 1)
    with pytest.raises(RunConflictError):
        mine.step(a, 1)
    # the stale copy was evicted: the retry rebuilds from the record and succeeds
    assert mine.step(a, 1)["run"]["cycle"] == 2


def test_replay_of_an_evicted_run_matches(toy_world, physics):
    manager = RunManager(toy_world, physics, max_runs=1, store=MemoryDocumentStore())
    a = _run_a(manager)
    manager.step(a, 1)
    head = manager.trace(a)["head"]
    same = manager.replay(a, {})
    assert manager.trace(same["run_id"])["head"] == head
    assert manager.summary(a)["rebuilt"] is True  # caching the replay evicted A
