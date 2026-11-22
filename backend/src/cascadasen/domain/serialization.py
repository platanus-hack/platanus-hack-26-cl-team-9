"""The one compact JSON encoding: no spaces, non-ASCII kept. Etags and audit hashes depend on its bytes."""

from __future__ import annotations

import json
from typing import Any


def dumps_compact(obj: Any, **kw: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), **kw)
