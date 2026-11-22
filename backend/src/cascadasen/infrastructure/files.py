"""File helpers shared by the exporters, the snapshot repository and the cache builders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cascadasen.domain.serialization import dumps_compact


def write_json(path: Path, obj: Any) -> int:
    """Write `obj` as compact UTF-8 JSON, creating parent folders. Returns the bytes written."""
    data = dumps_compact(obj).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)
