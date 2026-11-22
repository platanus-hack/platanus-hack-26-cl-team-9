"""JSON Schemas of the tools for an LLM that calls them directly (docs/assistant.md).

The MCP SDK derives these from the same signatures; this does it without the SDK. Schemas are cleaned
for Bedrock Converse: no `title`, and `T | None` collapses to an optional `T`.
"""

from __future__ import annotations

import inspect
from typing import Any, get_type_hints

from pydantic import create_model

from cascadasen.domain.ports import ToolSpec
from cascadasen.mcp.tools import TOOLS, Sub50Tools


def clean(node: Any) -> Any:
    if isinstance(node, list):
        return [clean(n) for n in node]
    if not isinstance(node, dict):
        return node
    options = node.get("anyOf")
    if options:
        kept = [o for o in options if o.get("type") != "null"]
        if len(kept) == 1:
            node = {**{k: v for k, v in node.items() if k != "anyOf"}, **kept[0]}
    return {k: clean(v) for k, v in node.items() if k not in ("title", "default")}


def describe(doc: str | None) -> str:
    return " ".join(inspect.cleandoc(doc or "").split())


def tool_specs(tools: Sub50Tools, exclude: frozenset[str] = frozenset()) -> list[ToolSpec]:
    specs = []
    for name in TOOLS:
        if name in exclude:
            continue
        method = getattr(tools, name)
        hints = get_type_hints(method)
        fields: dict[str, Any] = {
            p.name: (hints[p.name], ... if p.default is inspect.Parameter.empty else p.default)
            for p in inspect.signature(method).parameters.values()
        }
        schema = clean(create_model(name, **fields).model_json_schema())
        specs.append(ToolSpec(name, describe(method.__doc__), schema))
    return specs
