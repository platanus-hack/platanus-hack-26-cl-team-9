"""BoundedMap: the bounded map behind the session caches, the run cache and the campaign store."""

from cascadasen.application.cache import BoundedMap


def test_get_missing_is_none_and_put_evicts_the_oldest():
    cache = BoundedMap(2)
    assert cache.get("a") is None
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("c", 3)
    assert [cache.get(k) for k in "abc"] == [None, 2, 3]


def test_get_moves_the_entry_to_the_end():
    cache = BoundedMap(2)
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.get("a") == 1
    cache.put("c", 3)
    assert [cache.get(k) for k in "abc"] == [1, None, 3]


def test_put_existing_key_replaces_and_renews_it():
    cache = BoundedMap(2)
    cache.put("a", 1)
    cache.put("b", 2)
    cache.put("a", 10)
    cache.put("c", 3)
    assert [cache.get(k) for k in "abc"] == [10, None, 3]


def test_drop_removes_every_matching_key_and_only_those():
    cache = BoundedMap(10)
    cache.put("s1", 1)
    cache.put(("s1", 2), 2)
    cache.put(("s1", 3), 3)
    cache.put("s2", 4)
    cache.put(("s2", 1), 5)
    cache.drop(lambda k: k == "s1" or (isinstance(k, tuple) and k[0] == "s1"))
    assert [cache.get(k) for k in ("s1", ("s1", 2), ("s1", 3))] == [None, None, None]
    assert [cache.get(k) for k in ("s2", ("s2", 1))] == [4, 5]
    cache.drop(lambda k: False)
    assert cache.get("s2") == 4
