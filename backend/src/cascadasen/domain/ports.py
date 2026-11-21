"""Driven ports: what the application needs from the outside world.

Adapters in `cascadasen.infrastructure` implement these. Adding a data source means writing one
class that satisfies `GridDataSource`; nothing in domain or application changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from cascadasen.domain.model import GridSnapshot, SourceBundle, SourceInfo
from cascadasen.domain.regional import RegionalBundle


@runtime_checkable
class GridDataSource(Protocol):
    """One external dataset. `contribute` appends its records to the shared bundle."""

    source_id: str

    def contribute(self, bundle: SourceBundle, refresh: bool = False) -> SourceInfo: ...


@runtime_checkable
class RegionalGridSource(Protocol):
    """One country of the regional context layer (docs/regional.md). Returns raw-unit records."""

    country: str  # ISO 3166-1 alpha-3

    def fetch(self, refresh: bool = False) -> RegionalBundle: ...


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


class CommanderAdvisor(Protocol):
    """Optional C2 decision maker (docs/strategy.md 10). It only chooses among courses of action the
    deterministic validator already approved, up to C2's attention capacity; it never computes,
    validates or plays the adversary. Returns {"chosen": [option ids], "explanation": str} or None
    (unavailable, invalid, refused): the commander then falls back to its rules."""

    def choose(self, context: dict, options: list[dict], capacity: int) -> dict | None: ...


@dataclass(frozen=True)
class ToolSpec:
    """One tool the model may call: name, description and a JSON Schema for its arguments."""

    name: str
    description: str
    schema: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class AssistantTurn:
    """What the model answered: text and/or tool calls (an empty `tool_calls` ends the exchange)."""

    text: str
    tool_calls: tuple[ToolCall, ...] = ()


class ToolChatError(RuntimeError):
    """The model could not answer (unavailable, no tool support, refused). The message is shown as is."""


class ToolChatModel(Protocol):
    """An LLM that can call tools (docs/assistant.md). Messages are provider-neutral dicts:
    `{"role": "user", "text"}`, `{"role": "assistant", "text", "tool_calls": [{"id", "name",
    "arguments"}]}` and `{"role": "tool", "tool_call_id", "ok", "result"}`. Raises `ToolChatError`."""

    def turn(self, system: str, messages: list[dict[str, Any]], tools: list[ToolSpec]) -> AssistantTurn: ...


class ToolBox(Protocol):
    """The tools one conversation may use (docs/assistant.md). `run` never raises: a failed call is
    `(False, {"error": text})` and goes back to the model. `context` is the active session and run."""

    def specs(self) -> list[ToolSpec]: ...

    def run(self, call: ToolCall) -> tuple[bool, dict[str, Any]]: ...

    def context(self) -> dict[str, str | None]: ...


class ConflictError(RuntimeError):
    """A conditional write lost: the document changed (or already exists) since it was read."""


class DocumentStore(Protocol):
    """JSON documents by key with optimistic concurrency (sessions and run records). `put` with
    `if_match` writes only when the stored etag still matches; with `if_none_match` only when the key
    is absent. Both raise `ConflictError` otherwise. Expired documents read as missing."""

    def get(self, key: str) -> tuple[dict, str] | None: ...

    def put(
        self, key: str, doc: dict, *, if_match: str | None = None, if_none_match: bool = False
    ) -> str: ...

    def head(self, key: str) -> str | None: ...

    def delete(self, key: str) -> None: ...
