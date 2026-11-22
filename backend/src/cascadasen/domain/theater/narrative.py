"""Spanish narration from fixed templates (docs/stack.md 9; `params/narrative_es.yaml`).

`TemplateInterpreter` is the default `Interpreter` (domain/ports.py): it turns a run's report and
snapshots into a deterministic after-action review. An LLM-backed interpreter may implement the
same port later; it would explain, never decide (docs/strategy.md 10).
"""

from __future__ import annotations

from functools import cache
from typing import Any

from cascadasen.domain.simulation.params import load_params
from cascadasen.domain.theater.config import THEATER_DIR

LEVELS_ES = {
    "L0": "L0 · absorbido",
    "L1": "L1 · contenido",
    "L2": "L2 · apagón regional",
    "L3": "L3 · apagón nacional",
}


@cache
def templates() -> dict[str, Any]:
    return load_params("narrative_es", THEATER_DIR)


class _Keep(dict):
    def __missing__(self, key: str) -> str:
        return "?"


def num(x: float, decimals: int = 0) -> str:
    """Spanish number format: 1.234.567,8"""
    text = f"{x:,.{decimals}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def pct(x: float, decimals: int = 1) -> str:
    return f"{num(x * 100, decimals)} %"


def _fmt(value: Any) -> str:
    if isinstance(value, list | tuple):
        return ", ".join(_fmt(v) for v in value)
    if isinstance(value, float):
        return pct(value, 0) if 0 < value < 1 else num(value)
    return str(value)


def render(section: str, key: str, params: dict[str, Any] | None = None) -> str:
    tpl = templates().get(section, {}).get(key)
    if tpl is None:
        return key
    return tpl.format_map(_Keep({k: _fmt(v) for k, v in (params or {}).items()}))


def event_label(event_type: str) -> str:
    return render("event_types", event_type)


class TemplateInterpreter:
    """Deterministic after-action review in Spanish."""

    def after_action(self, report: dict[str, Any], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
        ind, con, coord = report["indicators"], report["consequence"], report["coordination"]
        sa = ind["situational_awareness"]
        cycle_min = (snapshots[1]["t_min"] - snapshots[0]["t_min"]) if len(snapshots) > 1 else 5
        summary = [
            f"La organización mantuvo el {pct(ind['mission_continuity'])} del servicio "
            f"(áreas prioritarias: {pct(ind['priority_continuity'])}).",
            (
                f"Tardó {sa['time_to_understanding_cycles']} ciclos "
                f"({sa['time_to_understanding_cycles'] * cycle_min} min) en comprender el incidente."
                if sa["time_to_understanding_cycles"] is not None
                else "No llegó a comprender el incidente dentro del horizonte."
            ),
            f"Peor nivel de consecuencia: {LEVELS_ES.get(con.get('worst_level', 'L0'), con.get('worst_level'))}.",
            f"Energía no servida: {num(con.get('unserved_energy_mwh', 0))} MWh; costo regulatorio "
            f"US$ {num(con.get('failure_cost_usd', 0))} (8,79 US$/kWh).",
            # a semicolon, not "1. Reserva": a reader (or an LLM) took "1." for list numbering
            f"Decisiones innecesarias: {ind['wrong_decisions']}; "
            f"reserva operacional final: {pct(ind['operational_reserve']['final'], 0)}.",
            f"Coordinación: {coord['conflicts']} conflictos, {coord['contradictions']} contradicciones, "
            f"{coord['blocked_at_execution']} acciones detenidas por el validador.",
        ]
        adversary = None
        if report.get("adversary"):
            adv = report["adversary"]
            mix = (
                ", ".join(f"{event_label(k)} ×{v}" for k, v in adv["strategy_mix"].items())
                or "ninguna acción"
            )
            kind = "adaptativo" if adv["adaptive"] else "estático"
            adversary = f"Adversario {kind} ({render('labels', adv['objective'])}): {mix}."
        timeline = []
        for s in snapshots:
            lines = [
                f"{event_label(e['type'])} en {e['area'] or e['target']}"
                + ("" if e["status"] == "established" else " (bloqueado)")
                for e in s["events"]
            ]
            lines += [
                render("actions", e["action"], {"target": e["target"]}) for e in s["executed"] if e["ok"]
            ]
            if lines:
                timeline.append({"cycle": s["cycle"], "t_min": s["t_min"], "lines": lines})
        return {
            "question": render("questions", report["run"]["question_key"]),
            "notice": templates()["notice"],
            "policy": render(
                "labels",
                f"policy_{report['run']['policy']}_"
                + {"A": "reactive", "B": "preventive", "C": "adaptive"}.get(report["run"]["policy"], ""),
            ),
            "summary": summary,
            "moments": [render("after_action", m["rationale_key"], m) for m in report["after_action"]],
            "adversary": adversary,
            "timeline": timeline,
            "experimental": True,
            **self._incident_section(report),
        }

    @staticmethod
    def _incident_section(report: dict[str, Any]) -> dict[str, Any]:
        inc = report.get("incident")
        if not inc:
            return {}
        card = inc["consequence_card"]
        effect = (
            f"{LEVELS_ES.get(card['consequence_level'], card['consequence_level'])}: hasta "
            f"{num(card['people_without_power'])} personas sin luz y {num(card['load_shed_mw'])} MW no servidos. "
            f"Con una interrupción supuesta de {num(card['outage_duration_h']['value'], 1)} h "
            f"(supuesto), {num(card['unserved_energy_mwh'])} MWh no servidos y US$ "
            f"{num(card['failure_cost_usd'])}."
        )
        prevention = [render("prevention", m) for m in inc["mitigations"]]
        return {
            "incident": {
                "title": inc["title"],
                "summary": render("labels", inc["summary_key"]),
                "effect": effect,
                "prevention": prevention,
                "notes": inc["notes"],
                "sources": inc["sources"],
                "verified": inc["verified"],
                "notices": inc["notices"],
            }
        }
