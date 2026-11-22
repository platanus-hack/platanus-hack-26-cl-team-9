"""Messages exchanged in the strategic cycle: courses of action, verdicts, intent, ISR picture,
field reports and action feedback. All immutable."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class COA:
    """A proposed course of action."""

    action: str
    target: str
    proposer: str
    rationale_key: str
    benefit: float = 1.0
    risk: float = 0.0
    params: tuple[tuple[str, Any], ...] = ()

    @property
    def key(self) -> str:
        return f"{self.action}:{self.target}"

    def param(self, name: str, default: Any = None) -> Any:
        return dict(self.params).get(name, default)

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "proposer": self.proposer,
            "rationale_key": self.rationale_key,
            "benefit": round(self.benefit, 3),
            "risk": round(self.risk, 3),
            "params": dict(self.params),
        }


@dataclass(frozen=True)
class Verdict:
    ok: bool
    code: str  # full reason, for the audit log and the evaluator
    observable_code: str  # what the proposer may learn
    side_effects: tuple[str, ...] = ()


@dataclass(frozen=True)
class Intent:
    escalation: int  # 0 normal, 1 alert, 2 crisis
    protect: tuple[str, ...]
    risk_tolerance: float
    reserve_keep: float
    allow_priority_shedding: bool
    rationale_key: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "escalation": self.escalation,
            "protect": list(self.protect),
            "risk_tolerance": self.risk_tolerance,
            "reserve_keep": self.reserve_keep,
            "allow_priority_shedding": self.allow_priority_shedding,
            "rationale_key": self.rationale_key,
        }


@dataclass(frozen=True)
class ISRReport:
    cycle: int
    p_intentional: float
    leading_cause: str  # none | failure | intentional
    confidence: float
    affected: tuple[str, ...]
    suspicion: tuple[tuple[str, float], ...]
    data_trust: tuple[tuple[str, float], ...]
    verify: tuple[str, ...]
    outages: tuple[str, ...]
    rationale_key: str

    def suspicion_of(self, area: str) -> float:
        return dict(self.suspicion).get(area, 0.0)

    def as_dict(self) -> dict[str, Any]:
        return {
            "p_intentional": round(self.p_intentional, 3),
            "leading_cause": self.leading_cause,
            "confidence": round(self.confidence, 3),
            "affected": list(self.affected),
            "verify": list(self.verify),
            "outages": list(self.outages),
            "rationale_key": self.rationale_key,
        }


@dataclass(frozen=True)
class FieldReport:
    """Ground truth a crew brings back from an area (it sees what supervision cannot)."""

    cycle: int
    area: str
    digital_issue: bool
    physical_issue: bool
    kinds: tuple[str, ...]


@dataclass(frozen=True)
class ActionFeedback:
    cycle: int
    action: str
    target: str
    ok: bool
    observable_code: str


@dataclass(frozen=True)
class Decision:
    coa: COA
    approved: bool
    reason: str
    verdict: Verdict
    conflicts_with: tuple[str, ...] = field(default=())

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.coa.as_dict(),
            "approved": self.approved,
            "reason": self.reason,
            "verdict": self.verdict.code,
            "side_effects": list(self.verdict.side_effects),
            "conflicts_with": list(self.conflicts_with),
        }
