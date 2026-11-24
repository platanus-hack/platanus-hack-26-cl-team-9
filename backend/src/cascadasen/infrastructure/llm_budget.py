"""Global cap on Bedrock calls (docs/assistant.md, Limits). One `CallBudget` per process is shared by the three
call sites: the assistant turn, the C2 commander and the after-action interpreter. A refused call raises
`LlmBudgetExceeded`; the commander and the interpreter already fall back to the rules on any exception, and
the assistant turns it into its usual model error. In memory, like `api/limits.py`."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable

from cascadasen.infrastructure.settings import Settings

MINUTE_S, DAY_S = 60.0, 86400.0


class LlmBudgetExceeded(Exception):
    """The per-minute or per-day cap on Bedrock calls is reached."""


class CallBudget:
    """At most `per_minute` calls in any 60 s and `per_day` in any 24 h (sliding windows)."""

    def __init__(self, per_minute: int, per_day: int, clock: Callable[[], float] = time.monotonic) -> None:
        self.per_minute, self.per_day, self.clock = per_minute, per_day, clock
        self._calls: deque[float] = deque()  # times of the calls of the last 24 h
        self._lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> CallBudget:
        return cls(settings.rate_llm_calls_per_minute, settings.rate_llm_calls_per_day)

    def spend(self) -> None:
        """Count one call, or raise `LlmBudgetExceeded` (a refused call is not counted)."""
        now = self.clock()
        with self._lock:
            while self._calls and self._calls[0] <= now - DAY_S:
                self._calls.popleft()
            last_minute = sum(1 for t in reversed(self._calls) if t > now - MINUTE_S)
            if len(self._calls) >= self.per_day or last_minute >= self.per_minute:
                raise LlmBudgetExceeded("Límite de llamadas al modelo alcanzado")
            self._calls.append(now)
