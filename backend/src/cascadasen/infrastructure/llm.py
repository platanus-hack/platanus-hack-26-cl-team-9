"""Optional LLM adapters (docs/strategy.md 10), off by default.

- `ClaudeCommander` implements `CommanderAdvisor`: C2 picks among courses of action the validator
  already approved, within its attention capacity, and explains the choice in Spanish.
- `ClaudeInterpreter` implements `Interpreter`: the template after-action review plus a short
  narrative in Spanish written from the run's report (never from the real state of a live run).

Both return None or the deterministic result on any failure (no key, timeout, refusal, bad JSON),
so the simulation never depends on the LLM. The `anthropic` package is the optional `llm` extra.
Enable with CASCADASEN_LLM_ENABLED=true and Anthropic credentials (ANTHROPIC_API_KEY or a profile).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from cascadasen.domain.ports import CommanderAdvisor, Interpreter
from cascadasen.domain.theater.narrative import TemplateInterpreter
from cascadasen.infrastructure.settings import Settings

log = logging.getLogger(__name__)

COMMANDER_SYSTEM = (
    "Eres el comandante (C2) de la sala de operaciones de una empresa eléctrica durante un incidente "
    "simulado. La misión es mantener el suministro dentro de condiciones seguras, conservar la "
    "supervisión y el control, proteger las áreas prioritarias, evitar que la contingencia se extienda "
    "y conservar capacidad de respuesta para recuperar. Ves solo lo que muestra la supervisión y lo que "
    "reporta tu equipo, que puede estar incompleto, atrasado o ser poco confiable. Todas las opciones ya "
    "pasaron el validador: elige cuáles ejecutar en este ciclo, como máximo la capacidad indicada, o "
    "ninguna si esperar es mejor. Prefiere medidas reversibles cuando la confianza es baja, no gastes "
    "recursos que harán falta para recuperar y no envíes cuadrillas que no llegarán a tiempo. Responde "
    "solo con el JSON pedido; la explicación, en español y en dos o tres frases."
)

INTERPRETER_SYSTEM = (
    "Redactas la revisión posterior de un ejercicio simulado de continuidad operacional de una empresa "
    "eléctrica. Escribe en español, en un párrafo de cinco a ocho frases, qué le pasó a la organización: "
    "cuándo entendió el incidente, qué decisiones ayudaron o costaron, qué recursos quedaron y qué "
    "aprender. Usa solo los datos entregados, no inventes cifras y no describas cómo se podría causar "
    "el incidente. Responde solo con el JSON pedido."
)

CHOICE_SCHEMA = {
    "type": "object",
    "properties": {
        "chosen": {"type": "array", "items": {"type": "string"}},
        "explanation": {"type": "string"},
    },
    "required": ["chosen", "explanation"],
    "additionalProperties": False,
}

NARRATIVE_SCHEMA = {
    "type": "object",
    "properties": {"narrative": {"type": "string"}},
    "required": ["narrative"],
    "additionalProperties": False,
}


class _Claude:
    def __init__(self, settings: Settings, client: Any = None) -> None:
        self.model, self.effort = settings.llm_model, settings.llm_effort
        if client is None:
            import anthropic  # optional extra: uv sync --extra llm

            client = anthropic.Anthropic(timeout=settings.llm_timeout_s, max_retries=1)
        self.client = client

    def _json(self, system: str, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any] | None:
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=4000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
                system=system,
                messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            )
            if response.stop_reason in ("refusal", "max_tokens"):
                log.warning("LLM stopped with %s; using the deterministic path", response.stop_reason)
                return None
            text = next(b.text for b in response.content if b.type == "text")
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except Exception as exc:
            log.warning("LLM unavailable (%s); using the deterministic path", type(exc).__name__)
            return None


class ClaudeCommander(_Claude):
    def choose(self, context: dict, options: list[dict], capacity: int) -> dict | None:
        payload = {"capacidad": capacity, "situacion": context, "opciones": options}
        return self._json(COMMANDER_SYSTEM, payload, CHOICE_SCHEMA)


class ClaudeInterpreter(_Claude):
    def __init__(self, settings: Settings, client: Any = None) -> None:
        super().__init__(settings, client)
        self.base = TemplateInterpreter()

    def after_action(self, report: dict, snapshots: list[dict]) -> dict:
        out = self.base.after_action(report, snapshots)
        data = self._json(
            INTERPRETER_SYSTEM,
            {"resumen": out["summary"], "momentos": out["moments"], "indicadores": report.get("indicators")},
            NARRATIVE_SCHEMA,
        )
        if data and isinstance(data.get("narrative"), str):
            return {**out, "narrative": data["narrative"], "interpreter": "llm"}
        return {**out, "interpreter": "template"}


def llm_adapters(settings: Settings) -> tuple[Interpreter | None, CommanderAdvisor | None]:
    """(interpreter, advisor) when enabled and the SDK is installed, else (None, None)."""
    if not settings.llm_enabled:
        return None, None
    try:
        return ClaudeInterpreter(settings), ClaudeCommander(settings)
    except ImportError:
        log.warning("CASCADASEN_LLM_ENABLED is set but `anthropic` is not installed (uv sync --extra llm)")
        return None, None
