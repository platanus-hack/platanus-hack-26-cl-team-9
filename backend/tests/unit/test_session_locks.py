"""SessionLocks (api/limits.py): one request at a time per session, 409 after the timeout."""

import threading
import time

import pytest
from fastapi import HTTPException

from cascadasen.api.limits import SessionLocks


def test_an_entry_is_freed_when_its_last_holder_exits():
    locks = SessionLocks(1.0)
    with locks.hold("a"):
        assert len(locks) == 1
    assert len(locks) == 0


def test_a_waiter_past_the_timeout_gets_409_with_retry_after():
    locks = SessionLocks(0.05)
    held, done = threading.Event(), threading.Event()

    def holder():
        with locks.hold("a"):
            held.set()
            done.wait(2)

    t = threading.Thread(target=holder)
    t.start()
    held.wait(2)
    with pytest.raises(HTTPException) as exc, locks.hold("a"):
        pass
    done.set()
    t.join()
    assert exc.value.status_code == 409 and exc.value.headers == {"Retry-After": "1"}
    assert "ocupada" in exc.value.detail and len(locks) == 0


def test_two_sessions_do_not_wait_for_each_other():
    locks = SessionLocks(0.05)
    with locks.hold("a"), locks.hold("b"):
        assert len(locks) == 2
    assert len(locks) == 0


def test_waiters_beyond_the_cap_get_409_at_once():
    locks = SessionLocks(5.0, max_waiters=1)
    held, done = threading.Event(), threading.Event()

    def holder():
        with locks.hold("a"):
            held.set()
            done.wait(5)

    def waiter():
        with locks.hold("a"):
            pass

    threads = [threading.Thread(target=holder), threading.Thread(target=waiter)]
    threads[0].start()
    held.wait(2)
    threads[1].start()
    while locks._locks["a"][1] < 2:  # the waiter is queued
        time.sleep(0.01)
    start = time.monotonic()
    with pytest.raises(HTTPException) as exc, locks.hold("a"):
        pass
    assert time.monotonic() - start < 1 and exc.value.status_code == 409
    done.set()
    for t in threads:
        t.join()
    assert len(locks) == 0


def test_the_default_cap_is_ten_waiters():
    from cascadasen.infrastructure.settings import Settings

    assert SessionLocks(1.0).max_waiters == 10 == Settings(_env_file=None).session_lock_max_waiters
