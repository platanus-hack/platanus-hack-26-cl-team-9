"""Auditor: reads frozen copies after each cycle and reports coordination findings.

It has no write path: it returns findings and the cycle engine appends them to the audit log. It
checks that every executed action had a valid verdict, and finds conflicts, decision delays and
contradictory decisions (an action undone within two cycles).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cascadasen.domain.theater.catalog import ACTIONS, Role

UNDOES = {
    "digital_segmentation": {"backup_comms"},
    "backup_comms": {"digital_segmentation"},
    "preventive_load_reduction": {"restore_element"},
    "restore_element": {"preventive_load_reduction", "islanding_prep"},
}


@dataclass(frozen=True)
class CycleRecord:
    """Frozen inputs the Auditor reads (built by the cycle engine)."""

    cycle: int
    decisions: tuple[dict[str, Any], ...]
    executed: tuple[dict[str, Any], ...]
    real_affected: tuple[str, ...]
    isr_affected: tuple[str, ...]


@dataclass
class AuditorAgent:
    role: Role = Role.AUDITOR
    onset: dict[str, int] = field(default_factory=dict)
    first_action: dict[str, int] = field(default_factory=dict)
    history: list[tuple[int, str, str]] = field(default_factory=list)  # (cycle, action, target)
    delays: list[int] = field(default_factory=list)
    conflicts: int = 0
    contradictions: int = 0
    violations: int = 0
    blocked: int = 0

    def audit(self, rec: CycleRecord) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for a in rec.real_affected:
            self.onset.setdefault(a, rec.cycle)
        for d in rec.decisions:
            if d["conflicts_with"]:
                self.conflicts += 1
                findings.append(
                    {
                        "kind": "conflict",
                        "key": f"{d['action']}:{d['target']}",
                        "against": d["conflicts_with"],
                        "rationale_key": "audit_conflict",
                    }
                )
        for e in rec.executed:
            action, target = e["action"], e["target"]
            if not e["ok"]:  # approved, then stopped by the validator at execution: the guard worked
                self.blocked += 1
                findings.append(
                    {
                        "kind": "blocked_at_execution",
                        "key": f"{action}:{target}",
                        "reason": e["verdict"],
                        "rationale_key": "audit_blocked_at_execution",
                    }
                )
                continue
            if e["verdict"] != "ok":
                self.violations += 1
                findings.append(
                    {
                        "kind": "constraint_violation",
                        "key": f"{action}:{target}",
                        "rationale_key": "audit_constraint_violation",
                    }
                )
            if not ACTIONS[action].info_only and target in self.onset and target not in self.first_action:
                self.first_action[target] = rec.cycle
                delay = rec.cycle - self.onset[target]
                self.delays.append(delay)
                findings.append(
                    {
                        "kind": "decision_delay",
                        "area": target,
                        "cycles": delay,
                        "rationale_key": "audit_decision_delay",
                    }
                )
            for c, prev_action, prev_target in self.history:
                if prev_target == target and rec.cycle - c <= 2 and prev_action in UNDOES.get(action, set()):
                    self.contradictions += 1
                    findings.append(
                        {
                            "kind": "contradiction",
                            "key": f"{action}:{target}",
                            "undoes": prev_action,
                            "rationale_key": "audit_contradiction",
                        }
                    )
            self.history.append((rec.cycle, action, target))
        missed = sorted(set(rec.real_affected) - set(rec.isr_affected))
        if missed:
            findings.append({"kind": "blind_spot", "areas": missed, "rationale_key": "audit_blind_spot"})
        return findings

    def summary(self) -> dict[str, Any]:
        return {
            "conflicts": self.conflicts,
            "contradictions": self.contradictions,
            "constraint_violations": self.violations,
            "blocked_at_execution": self.blocked,
            "mean_decision_delay_cycles": round(sum(self.delays) / len(self.delays), 2)
            if self.delays
            else None,
        }
