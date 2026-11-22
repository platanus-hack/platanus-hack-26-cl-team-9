"""Append-only, hash-chained audit log (docs/strategy.md section 7).

Each entry stores the hash of the previous one; changing any past entry breaks every hash after it.
The Auditor agent never writes here: the cycle engine appends what the Auditor reports.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from cascadasen.domain.serialization import dumps_compact

GENESIS = "0" * 64


def _plain(obj: Any) -> Any:
    if isinstance(obj, float):
        return round(obj, 6)
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple | set | frozenset):
        items = [_plain(v) for v in obj]
        return sorted(items, key=json.dumps) if isinstance(obj, set | frozenset) else items
    return obj


def canonical(obj: Any) -> str:
    return dumps_compact(_plain(obj), sort_keys=True, default=str)


@dataclass
class AuditLog:
    entries: list[dict[str, Any]] = field(default_factory=list)

    @property
    def head(self) -> str:
        return self.entries[-1]["hash"] if self.entries else GENESIS

    def append(
        self, cycle: int, phase: str, actor: str, kind: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        body = {
            "seq": len(self.entries),
            "cycle": cycle,
            "phase": phase,
            "actor": actor,
            "kind": kind,
            "payload": _plain(payload),
            "prev": self.head,
        }
        body["hash"] = hashlib.sha256(canonical(body).encode()).hexdigest()
        self.entries.append(body)
        return body

    def verify(self) -> bool:
        prev = GENESIS
        for i, e in enumerate(self.entries):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e["seq"] != i or e["prev"] != prev:
                return False
            if hashlib.sha256(canonical(body).encode()).hexdigest() != e["hash"]:
                return False
            prev = e["hash"]
        return True
