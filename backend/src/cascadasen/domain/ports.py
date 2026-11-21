"""Driven ports: what the application needs from the outside world.

Adapters in `cascadasen.infrastructure` implement these. Adding a data source means writing one
class that satisfies `GridDataSource`; nothing in domain or application changes.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cascadasen.domain.model import GridSnapshot, SourceBundle, SourceInfo


@runtime_checkable
class GridDataSource(Protocol):
    """One external dataset. `contribute` appends its records to the shared bundle."""

    source_id: str

    def contribute(self, bundle: SourceBundle, refresh: bool = False) -> SourceInfo: ...


class SnapshotRepository(Protocol):
    def save(self, snapshot: GridSnapshot) -> None: ...

    def load(self) -> GridSnapshot | None: ...


class ContractExporter(Protocol):
    """Writes derived artefacts (e.g. the frontend network.json contract)."""

    def export(self, snapshot: GridSnapshot) -> list[str]: ...


class Interpreter(Protocol):
    """Explains a finished run (docs/strategy.md 10). The default is template-based and
    deterministic; an LLM-backed adapter may implement it, but never decides or computes."""

    def after_action(self, report: dict, snapshots: list[dict]) -> dict: ...
