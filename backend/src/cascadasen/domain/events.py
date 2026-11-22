"""The event record shared by both engines: `{t, type, ids, text_key, params}`."""

from __future__ import annotations

from typing import Any


def make_event(
    t: float, kind: str, ids: list[str], text_key: str | None = None, *, ndigits: int = 3, **params: Any
) -> dict[str, Any]:
    """One timeline event. `text_key` (the narration template) defaults to `kind`; `t` is rounded to
    `ndigits` (3 in the 13-area engine, 2 in the cascade engine)."""
    return {"t": round(t, ndigits), "type": kind, "ids": ids, "text_key": text_key or kind, "params": params}
