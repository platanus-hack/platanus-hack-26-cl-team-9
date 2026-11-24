"""Optional LLM adapters (docs/strategy.md 10), off by default.

- `ClaudeCommander` implements `CommanderAdvisor`: C2 picks among courses of action the validator
  already approved, within its attention capacity, and explains the choice in Spanish.
- `ClaudeInterpreter` implements `Interpreter`: the template after-action review plus a short
  narrative in Spanish written from the run's report (never from the real state of a live run).

Both return None or the deterministic result on any failure (no credentials, timeout, refusal, bad
JSON), so the simulation never depends on the LLM. The `anthropic[bedrock]` package is the optional
`llm` extra. Providers (CASCADASEN_LLM_PROVIDER):

- `anthropic`: the Claude API (ANTHROPIC_API_KEY or an `ant auth login` profile), with the server-side
  refusal fallback;
- `bedrock`: Amazon Bedrock through `AnthropicBedrockMantle`, with the AWS profile and region of
  CASCADASEN_AWS_PROFILE / CASCADASEN_AWS_REGION (credentials stay in ~/.aws). Bedrock model ids carry
  the `anthropic.` prefix and Bedrock has no server-side fallbacks, so they are not sent;
- `bedrock-converse`: any Bedrock text model (Amazon Nova, Llama, Mistral, Claude...) through the
  Bedrock Converse API with boto3. CASCADASEN_LLM_MODEL is the Bedrock model or inference-profile id as
  is (for example `amazon.nova-pro-v1:0` or `us.amazon.nova-pro-v1:0`). The JSON answer is requested as
  a forced tool call with the schema; models that do not support that get the schema in the prompt.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from cascadasen.domain.ports import CommanderAdvisor, Interpreter
from cascadasen.domain.theater.narrative import TemplateInterpreter
from cascadasen.infrastructure.llm_budget import CallBudget
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


BEDROCK_PREFIX = "anthropic."


CONVERSE = "bedrock-converse"


def model_id(settings: Settings) -> str:
    m = settings.llm_model
    return m if settings.llm_provider != "bedrock" or m.startswith(BEDROCK_PREFIX) else BEDROCK_PREFIX + m


def make_client(settings: Settings) -> Any:
    if settings.llm_provider == CONVERSE:
        import boto3  # optional extra: uv sync --extra llm
        from botocore.config import Config

        session = boto3.Session(profile_name=settings.aws_profile or None)  # None: env vars first
        return session.client(
            "bedrock-runtime",
            region_name=settings.aws_region or None,
            config=Config(read_timeout=settings.llm_timeout_s, retries={"max_attempts": 1}),
        )
    import anthropic  # optional extra: uv sync --extra llm

    if settings.llm_provider == "bedrock":
        return anthropic.AnthropicBedrockMantle(
            aws_profile=settings.aws_profile or None,  # None: standard AWS chain (env vars first)
            aws_region=settings.aws_region or None,
            timeout=settings.llm_timeout_s,
            max_retries=1,
        )
    return anthropic.Anthropic(timeout=settings.llm_timeout_s, max_retries=1)


class _Claude:
    def __init__(self, settings: Settings, client: Any = None, budget: CallBudget | None = None) -> None:
        self.budget = budget if budget is not None else CallBudget.from_settings(settings)
        self.model, self.effort = model_id(settings), settings.llm_effort
        self.bedrock = settings.llm_provider == "bedrock"
        self.converse = settings.llm_provider == CONVERSE
        self.client = client if client is not None else make_client(settings)

    def _create(self, **request: Any) -> Any:
        if self.bedrock:  # no server-side fallbacks on Bedrock: a refusal falls back to the rules
            return self.client.messages.create(**request)
        return self.client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request
        )

    def _converse(
        self, system: str, payload: dict[str, Any], schema: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Bedrock Converse: ask for a forced tool call carrying the JSON; if the model does not support
        forced tools, ask again with the schema in the prompt and parse the text."""
        user = [{"role": "user", "content": [{"text": json.dumps(payload, ensure_ascii=False)}]}]
        request = {
            "modelId": self.model,
            "messages": user,
            "inferenceConfig": {"maxTokens": 2000, "temperature": 0.2},
        }
        tool = {
            "toolSpec": {
                "name": "responder",
                "description": "Entrega la respuesta.",
                "inputSchema": {"json": schema},
            }
        }
        self.budget.spend()  # over the cap: raises, and _json falls back to the rules
        try:
            out = self.client.converse(
                system=[{"text": system}],
                toolConfig={"tools": [tool], "toolChoice": {"tool": {"name": "responder"}}},
                **request,
            )
        except Exception as exc:
            if type(exc).__name__ != "ValidationException":
                raise
            prompt = (
                f"{system}\nResponde solo con un objeto JSON que cumpla este esquema: {json.dumps(schema)}"
            )
            self.budget.spend()
            out = self.client.converse(system=[{"text": prompt}], **request)
        for block in out["output"]["message"]["content"]:
            if "toolUse" in block and isinstance(block["toolUse"].get("input"), dict):
                return block["toolUse"]["input"]
            if "text" in block:
                text = block["text"].strip().removeprefix("```json").removeprefix("```").removesuffix("```")
                start, end = text.find("{"), text.rfind("}")
                if start >= 0 and end > start:
                    data = json.loads(text[start : end + 1])
                    return data if isinstance(data, dict) else None
        return None

    def _json(self, system: str, payload: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any] | None:
        try:
            if self.converse:
                return self._converse(system, payload, schema)
            response = self._create(
                model=self.model,
                max_tokens=4000,
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
    def __init__(self, settings: Settings, client: Any = None, budget: CallBudget | None = None) -> None:
        super().__init__(settings, client, budget)
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


def llm_adapters(
    settings: Settings, budget: CallBudget | None = None
) -> tuple[Interpreter | None, CommanderAdvisor | None]:
    """(interpreter, advisor) when enabled and the SDK is installed, else (None, None). They share `budget`."""
    if not settings.llm_enabled:
        return None, None
    budget = budget if budget is not None else CallBudget.from_settings(settings)
    try:
        return ClaudeInterpreter(settings, budget=budget), ClaudeCommander(settings, budget=budget)
    except ImportError:
        log.warning("CASCADASEN_LLM_ENABLED is set but `anthropic` is not installed (uv sync --extra llm)")
        return None, None
    except Exception as exc:
        log.warning("LLM client could not be built (%s); using the deterministic path", type(exc).__name__)
        return None, None
