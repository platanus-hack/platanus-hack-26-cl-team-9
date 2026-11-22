"""In-app natural-language assistant (docs/assistant.md): one chat message runs a tool-use loop.

The model sees only tool results (compact summaries from the agent API) and calls the same tools the
MCP server exposes. Conversations are documents in the `DocumentStore` (`assistant/<cid>.json`), so any
instance can continue one. The loop is capped by steps and by a deadline shorter than the proxy timeout.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from cascadasen.application.sessions import SESSION_ID
from cascadasen.domain.ports import ConflictError, DocumentStore, ToolBox, ToolChatError, ToolChatModel

log = logging.getLogger(__name__)

MAX_RESULT_CHARS = 8000
FAILED_TURN = "(No pude responder a este mensaje por un error del modelo.)"
LIMIT_REPLY = {
    "steps": "Llegué al límite de pasos de este mensaje. Dime «continúa» y sigo desde donde quedé.",
    "deadline": "Se acabó el tiempo de este mensaje. Dime «continúa» y sigo desde donde quedé.",
}


NUDGE = (
    "(Mensaje interno, el usuario no lo ve.) Anunciaste una acción pero no la ejecutaste. Ejecútala "
    "ahora con las herramientas y luego informa el resultado; no la vuelvas a anunciar."
)
# First-person future of the actions the assistant can take ("cortaré", "voy a agregar"). A list, not
# a suffix rule: "-aré" also ends past forms such as "reparé" or "comparé".
FUTURE_ACTION = re.compile(
    r"\b(voy a|vamos a|procedo a|proceder[ée]|cortar[ée]|abrir[ée]|agregar[ée]|añadir[ée]|quitar[ée]|"
    r"eliminar[ée]|reparar[ée]|crear[ée]|iniciar[ée]|inyectar[ée]|disparar[ée]|avanzar[ée]|ejecutar[ée]|"
    r"simular[ée]|revisar[ée]|consultar[ée]|buscar[ée]|calcular[ée]|comparar[ée]|repetir[ée]|har[ée])\b",
    re.IGNORECASE,
)


# Offers that wait for the user ("dime qué quieres y lo haré") are not unkept promises.
OFFER = re.compile(
    r"(\bdime\b|\bsi quieres\b|\bsi deseas\b|\bsi prefieres\b|\bcuando (?:me )?indiques\b|¿)", re.I
)


def announces(text: str) -> bool:
    """The model ended its turn promising an action instead of asking or offering something."""
    return bool(FUTURE_ACTION.search(text)) and not OFFER.search(text) and not text.rstrip().endswith("?")


class Emitter:
    """Calls the streaming callback, if any. A failing callback (a client that went away) never stops
    the loop: the conversation still runs to the end and is saved."""

    def __init__(self, callback: Callable[[str, dict[str, Any]], None] | None) -> None:
        self.callback = callback

    def __call__(self, kind: str, data: dict[str, Any]) -> None:
        if self.callback is None:
            return
        try:
            self.callback(kind, data)
        except Exception:
            log.debug("stream callback dropped", exc_info=True)
            self.callback = None


class ConversationNotFoundError(KeyError):
    pass


class ConversationConflictError(RuntimeError):
    """Two messages of the same conversation ran at once; the second one lost."""


class AssistantInputError(ValueError):
    pass


def key(cid: str) -> str:
    return f"assistant/{cid}.json"


def trim_result(result: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(result, ensure_ascii=False)
    if len(text) <= MAX_RESULT_CHARS:
        return result
    return {"truncated": True, "preview": text[:MAX_RESULT_CHARS]}


def trim_history(messages: list[dict[str, Any]], keep: int) -> list[dict[str, Any]]:
    """The last `keep` messages, starting at a user turn so no tool result loses its call."""
    if len(messages) <= keep:
        return messages
    tail = messages[-keep:]
    start = next((i for i, m in enumerate(tail) if m["role"] == "user"), len(tail))
    return tail[start:]


def view(doc: dict[str, Any]) -> dict[str, Any]:
    """What a client may read back: the visible turns and the tool trace."""
    turns = [
        {"role": m["role"], "text": m["text"]}
        for m in doc["messages"]
        if m["role"] in ("user", "assistant") and m.get("text") and not m.get("hidden")
    ]
    calls = {c["id"]: c for m in doc["messages"] for c in m.get("tool_calls", [])}
    trace = [
        {
            "name": calls[m["tool_call_id"]]["name"],
            "arguments": calls[m["tool_call_id"]]["arguments"],
            "ok": m["ok"],
            "result": m["result"],
        }
        for m in doc["messages"]
        if m["role"] == "tool" and m["tool_call_id"] in calls
    ]
    return {
        "conversation_id": doc["conversation_id"],
        "session_id": doc.get("session_id"),
        "run_id": doc.get("run_id"),
        "turns": turns,
        "tool_calls": trace,
    }


class Assistant:
    def __init__(
        self,
        model: ToolChatModel,
        store: DocumentStore,
        system: str,
        *,
        max_steps: int = 8,
        deadline_s: float = 25.0,
        history_messages: int = 30,
        notice: str = "",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.model, self.store, self.system = model, store, system
        self.max_steps, self.deadline_s, self.history = max_steps, deadline_s, history_messages
        self.notice, self.clock = notice, clock

    def load(self, cid: str) -> tuple[dict[str, Any], str]:
        found = self.store.get(key(cid))
        if found is None:
            raise ConversationNotFoundError(cid)
        return found

    def delete(self, cid: str) -> None:
        self.load(cid)
        self.store.delete(key(cid))

    def chat(
        self,
        message: str,
        conversation_id: str | None,
        session_id: str | None,
        toolbox_for: Callable[[str | None, str | None], ToolBox],
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
        deadline_s: float | None = None,
    ) -> dict[str, Any]:
        """Run one user message. `toolbox_for(session_id, run_id)` builds the tools of this request;
        `on_event(kind, data)` receives the steps
        as they happen (`start`, `assistant_text`, `tool_call`, `tool_result`) for streaming clients;
        `deadline_s` overrides the default deadline (a stream keeps the connection alive longer)."""
        if session_id is not None and not SESSION_ID.match(session_id):
            raise AssistantInputError("El id de sesión no es válido.")
        if conversation_id is None:
            cid, etag = secrets.token_urlsafe(16), None
            doc: dict[str, Any] = {
                "conversation_id": cid,
                "messages": [],
                "session_id": None,
                "run_id": None,
                "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
        else:
            cid = conversation_id
            doc, etag = self.load(cid)
        if session_id and session_id != doc.get("session_id"):
            doc["session_id"], doc["run_id"] = session_id, None
        toolbox = toolbox_for(doc.get("session_id"), doc.get("run_id"))
        messages = trim_history(doc["messages"], self.history)
        messages.append({"role": "user", "text": message})
        start = len(messages) - 1  # this turn's messages, for the trace
        emit = Emitter(on_event)
        emit("start", {"conversation_id": cid, **toolbox.context()})
        failure: ToolChatError | None = None
        try:
            reply, truncated, steps = self.loop(messages, toolbox, emit, deadline_s or self.deadline_s)
        except ToolChatError as exc:  # keep the turn so the user can retry; roles keep alternating
            failure = exc
            messages.append({"role": "assistant", "text": FAILED_TURN})
            reply, truncated, steps = "", None, 0
        doc["messages"] = trim_history(messages, self.history)
        doc.update(toolbox.context())
        doc["updated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        self.save(cid, doc, etag)
        if failure is not None:
            raise failure
        return {
            "tool_calls": view({"messages": messages[start:], "conversation_id": cid})["tool_calls"],
            "conversation_id": cid,
            "session_id": doc.get("session_id"),
            "run_id": doc.get("run_id"),
            "reply": reply,
            "steps": steps,
            "truncated": truncated,
            "notice": self.notice,
        }

    def loop(
        self,
        messages: list[dict[str, Any]],
        toolbox: ToolBox,
        emit: Emitter | None = None,
        deadline_s: float | None = None,
    ) -> tuple[str, str | None, int]:
        emit, deadline_s = emit or Emitter(None), deadline_s or self.deadline_s
        started, specs, nudged = self.clock(), toolbox.specs(), False
        durations: list[float] = []
        for step in range(1, self.max_steps + 1):
            # do not start a model call that would likely end past the deadline (mean of this turn's calls;
            # the slowest one alone is too pessimistic after a single outlier)
            expected = sum(durations) / len(durations) if durations else 0.0
            if self.clock() - started + expected > deadline_s:
                return self.stop(messages, "deadline", step - 1)
            call_started = self.clock()
            turn = self.model.turn(self.system, messages, specs)
            durations.append(self.clock() - call_started)
            messages.append(
                {
                    "role": "assistant",
                    "text": turn.text,
                    "tool_calls": [
                        {"id": c.id, "name": c.name, "arguments": c.arguments} for c in turn.tool_calls
                    ],
                }
            )
            if not turn.tool_calls:
                if not nudged and step < self.max_steps and announces(turn.text):
                    nudged = True  # it promised an action and stopped: ask once, out of the user's sight
                    messages.append({"role": "user", "text": NUDGE, "hidden": True})
                    continue
                return turn.text, None, step
            if turn.text:  # what the model says while it works ("abro el corredor…")
                emit("assistant_text", {"step": step, "text": turn.text})
            for call in turn.tool_calls:
                emit(
                    "tool_call", {"step": step, "id": call.id, "name": call.name, "arguments": call.arguments}
                )
                ok, result = toolbox.run(call)
                trimmed = trim_result(result)
                messages.append({"role": "tool", "tool_call_id": call.id, "ok": ok, "result": trimmed})
                emit(
                    "tool_result",
                    {
                        "step": step,
                        "id": call.id,
                        "name": call.name,
                        "ok": ok,
                        "result": trimmed,
                        **toolbox.context(),  # where to fetch the full data: session and run ids
                    },
                )
        return self.stop(messages, "steps", self.max_steps)

    @staticmethod
    def stop(messages: list[dict[str, Any]], reason: str, steps: int) -> tuple[str, str, int]:
        text = LIMIT_REPLY[reason]
        messages.append({"role": "assistant", "text": text})  # keeps user/assistant turns alternating
        return text, reason, steps

    def save(self, cid: str, doc: dict[str, Any], etag: str | None) -> None:
        try:
            self.store.put(key(cid), doc, if_match=etag, if_none_match=etag is None)
        except ConflictError as exc:
            raise ConversationConflictError(cid) from exc
