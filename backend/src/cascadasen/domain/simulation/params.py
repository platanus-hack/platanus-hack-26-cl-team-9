"""Parameter files with mandatory provenance.

Every number in a parameter file must sit in the `value` field of a mapping that also carries a
non-empty `source` or `is_assumption: true` (docs/datasets.md section 6). The loader rejects a
bare number, naming the file and the field (docs/stack.md section 7).
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

PARAMS_DIR = Path(__file__).parent / "params"
STRUCTURAL_KEYS = {"version"}


class ParameterError(ValueError):
    """A parameter file is malformed or has a number without provenance."""


@dataclass(frozen=True)
class Provenance:
    key: str
    source: str | None
    is_assumption: bool
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"key": self.key, "source": self.source, "is_assumption": self.is_assumption}
        if self.note:
            out["note"] = self.note
        return out


def _is_number(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


def check_provenance(tree: Any, where: str, path: str = "") -> None:
    """Raise ParameterError when a number is not wrapped in a provenance-carrying `value`."""
    if isinstance(tree, dict):
        if "value" in tree:
            if not (tree.get("source") or tree.get("is_assumption") is True):
                raise ParameterError(f"{where}: '{path}' has a value without source or is_assumption")
            return
        for k, v in tree.items():
            if k in STRUCTURAL_KEYS and not path:
                continue
            check_provenance(v, where, f"{path}.{k}" if path else str(k))
    elif isinstance(tree, list):
        for i, v in enumerate(tree):
            check_provenance(v, where, f"{path}[{i}]")
    elif _is_number(tree):
        raise ParameterError(f"{where}: '{path}' is a bare number ({tree}); wrap it with value + source")


@cache
def load_params(name: str) -> dict[str, Any]:
    """Load and validate `params/<name>.yaml`. Cached: files are read once per process."""
    path = PARAMS_DIR / f"{name}.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ParameterError(f"{path.name}: cannot load ({exc})") from exc
    if not isinstance(data, dict):
        raise ParameterError(f"{path.name}: top level must be a mapping")
    check_provenance(data, path.name)
    return data


def value(node: dict[str, Any], key: str = "") -> Any:
    """Return the `value` of a provenance-carrying mapping."""
    if not isinstance(node, dict) or "value" not in node:
        raise ParameterError(f"'{key}' is not a parameter mapping with a value")
    return node["value"]


def provenance(node: dict[str, Any], key: str) -> Provenance:
    return Provenance(
        key=key,
        source=node.get("source"),
        is_assumption=bool(node.get("is_assumption", False)),
        note=str(node.get("note", "")),
    )


def collect_provenance(tree: Any, prefix: str = "") -> list[Provenance]:
    """All parameter mappings in a tree, as provenance records (for timeline.json `provenance`)."""
    out: list[Provenance] = []
    if isinstance(tree, dict):
        if "value" in tree:
            return [provenance(tree, prefix)]
        for k, v in tree.items():
            if k in STRUCTURAL_KEYS and not prefix:
                continue
            out.extend(collect_provenance(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(tree, list):
        for i, v in enumerate(tree):
            out.extend(collect_provenance(v, f"{prefix}[{i}]"))
    return out
