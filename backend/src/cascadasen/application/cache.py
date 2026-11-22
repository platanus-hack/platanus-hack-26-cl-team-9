"""One bounded, thread-safe map: the session caches, the run cache and the campaign store use it."""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any


class BoundedMap[K, V]:
    """Keeps the `size` newest entries. `get` renews an entry (LRU) unless `touch=False` (FIFO)."""

    def __init__(self, size: int) -> None:
        self.size = size
        self._items: OrderedDict[K, V] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: K, *, touch: bool = True) -> V | None:
        with self._lock:
            if key not in self._items:
                return None
            if touch:
                self._items.move_to_end(key)
            return self._items[key]

    def put(self, key: K, value: V) -> None:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self.size:
                self._items.popitem(last=False)

    def pop(self, key: K) -> None:
        with self._lock:
            self._items.pop(key, None)

    def drop(self, match: Callable[[Any], bool]) -> None:
        with self._lock:
            for key in [k for k in self._items if match(k)]:
                del self._items[key]

    def __len__(self) -> int:
        return len(self._items)
