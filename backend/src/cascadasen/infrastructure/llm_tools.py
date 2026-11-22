"""Tool-calling LLM adapter for the in-app assistant (docs/assistant.md): Amazon Bedrock Converse.

Implements `ToolChatModel` over any Bedrock model that supports tool use (the model id is passed as is,
like `bedrock-converse` in `llm.py`). Credentials come from the AWS chain, never from settings.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from cascadasen.domain.ports import AssistantTurn, ToolCall, ToolChatError, ToolSpec
from cascadasen.infrastructure.llm import CONVERSE, make_client
from cascadasen.infrastructure.settings import Settings

log = logging.getLogger(__name__)

MAX_TOKENS = 2000
# DeepSeek on Converse sometimes leaks the start of its own tool-call markup ("<｜DSML｜function_calls", with
# fullwidth bars) into the text block next to a real toolUse block. Everything from the marker on is markup.
LEAKED_MARKUP = re.compile(r"<｜[^｜>]*｜")


def clean_text(text: str) -> str:
    """The model's visible text without leaked tool-call markup."""
    match = LEAKED_MARKUP.search(text)
    return (text[: match.start()] if match else text).strip()


def _result_block(msg: dict[str, Any]) -> dict[str, Any]:
    result = msg["result"] if isinstance(msg["result"], dict) else {"result": msg["result"]}
    return {
        "toolResult": {
            "toolUseId": msg["tool_call_id"],
            "content": [{"json": result}],
            "status": "success" if msg["ok"] else "error",
        }
    }


def to_converse(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Neutral messages to Converse: tool results merge into one user message, empty text is dropped."""
    out: list[dict[str, Any]] = []
    for msg in messages:
        role = msg["role"]
        if role == "tool":
            block = _result_block(msg)
            if out and out[-1]["role"] == "user" and "toolResult" in out[-1]["content"][0]:
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
        elif role == "assistant":
            content: list[dict[str, Any]] = [{"text": msg["text"]}] if msg.get("text") else []
            content += [
                {"toolUse": {"toolUseId": c["id"], "name": c["name"], "input": c["arguments"]}}
                for c in msg.get("tool_calls", [])
            ]
            out.append({"role": "assistant", "content": content or [{"text": "."}]})
        else:
            out.append({"role": "user", "content": [{"text": msg["text"]}]})
    return out


def describe(exc: Exception) -> str:
    """For the server log only (never sent to the client): the exception name and, for an AWS error,
    its code and message. They carry no credentials."""
    error = (
        getattr(exc, "response", {}).get("Error", {})
        if isinstance(getattr(exc, "response", None), dict)
        else {}
    )
    detail = f"{error.get('Code', '')} {error.get('Message', '')}".strip() or str(exc)
    return f"{type(exc).__name__}: {detail[:300]}"


class ConverseToolChat:
    def __init__(self, model: str, client: Any) -> None:
        self.model, self.client = model, client

    def turn(self, system: str, messages: list[dict[str, Any]], tools: list[ToolSpec]) -> AssistantTurn:
        specs = [
            {"toolSpec": {"name": t.name, "description": t.description, "inputSchema": {"json": t.schema}}}
            for t in tools
        ]
        try:
            out = self.client.converse(
                modelId=self.model,
                system=[{"text": system}],
                messages=to_converse(messages),
                toolConfig={"tools": specs},
                inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": 0.2},
            )
        except Exception as exc:
            name = type(exc).__name__
            log.warning("assistant LLM call failed for %s: %s", self.model, describe(exc))
            if name == "ValidationException":
                raise ToolChatError("El modelo configurado no acepta herramientas o la solicitud.") from exc
            raise ToolChatError("El modelo de lenguaje no está disponible ahora; reintenta.") from exc
        blocks = out["output"]["message"]["content"]
        text = clean_text("\n".join(b["text"] for b in blocks if "text" in b))
        calls = tuple(
            ToolCall(u["toolUseId"], u["name"], u["input"] if isinstance(u.get("input"), dict) else {})
            for u in (b["toolUse"] for b in blocks if "toolUse" in b)
        )
        return AssistantTurn(text, calls)


def tool_chat(settings: Settings, client: Any = None) -> ConverseToolChat | None:
    """The assistant's model when the LLM is enabled with `bedrock-converse` and boto3 is available."""
    if not settings.llm_enabled or settings.llm_provider != CONVERSE:
        return None
    try:
        tuned = settings.model_copy(update={"llm_timeout_s": settings.assistant_call_timeout_s})
        return ConverseToolChat(settings.llm_model, client if client is not None else make_client(tuned))
    except ImportError:
        log.warning("The assistant needs boto3 (uv sync --extra llm)")
        return None
    except Exception as exc:
        log.warning("The assistant's LLM client could not be built (%s)", type(exc).__name__)
        return None
