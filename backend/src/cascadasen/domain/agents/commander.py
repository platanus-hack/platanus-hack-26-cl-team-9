"""C2 Commander: sets intent, gates proposals by the policy's confidence thresholds, resolves
conflicts and decides within its attention capacity. It cannot override the validator."""

from __future__ import annotations

from collections.abc import Callable

from cascadasen.domain.agents.base import AgentView
from cascadasen.domain.theater.areas import TheaterNetwork
from cascadasen.domain.theater.catalog import ACTIONS, CONFLICTS, Role
from cascadasen.domain.theater.decisions import COA, Decision, Intent, ISRReport, Verdict

MISSION_FIRST = ("restore_element", "backup_comms", "manual_operation")
SAFETY_FIRST = ("digital_segmentation", "preventive_load_reduction", "islanding_prep")
RISK_TOLERANCE = {"A": 0.3, "B": 0.1, "C": 0.2}


CONTAINMENT_CONFIDENCE = 0.75  # assumption: above every policy threshold but A heavy (0.8)


class CommanderAgent:
    role = Role.C2

    def __init__(self, network: TheaterNetwork, plan_load: dict[str, float]) -> None:
        self.net = network
        self.estimate = dict(plan_load)  # what C2 believes each area is serving
        self.intent_now: Intent | None = None

    def observe(self, view: AgentView) -> None:
        for o in view.observed.areas:
            if o.energized is False:
                self.estimate[o.area] = 0.0
            elif o.served_mw is not None:
                self.estimate[o.area] = o.served_mw

    def intent(self, view: AgentView) -> Intent:
        isr, mission, policy = view.isr, view.mission, view.policy
        load = sum(o.load_mw for o in view.observed.areas)
        continuity = sum(self.estimate.values()) / load if load else 1.0
        escalation, key = 0, "intent_normal"
        if isr and (isr.affected or isr.outages):
            escalation, key = 1, "intent_alert"
        if isr and (
            (isr.leading_cause == "intentional" and isr.confidence >= 0.7 and len(isr.affected) >= 2)
            or continuity < mission.continuity_threshold
        ):
            escalation, key = 2, "intent_crisis"
        self.intent_now = Intent(
            escalation=escalation,
            protect=mission.priority_areas,
            risk_tolerance=RISK_TOLERANCE.get(policy.id, 0.2),
            reserve_keep=policy.reserve_keep,
            allow_priority_shedding=escalation == 2 and policy.preventive,
            rationale_key=key,
        )
        return self.intent_now

    @staticmethod
    def confidence(isr: ISRReport | None, coa: COA, view: AgentView) -> float:
        """How sure C2 is that the target needs this action."""
        if coa.action == "rearm_defense" or ACTIONS[coa.action].weight == "restore":
            return 1.0
        if isr is None:
            return 0.0
        area = coa.target
        c = isr.suspicion_of(area)
        if area in isr.outages:
            c = 1.0
        if area in isr.affected and isr.leading_cause != "none":
            c = max(c, isr.confidence)  # the area is part of the picture ISR is confident about
        if any(r.area == area and (r.digital_issue or r.physical_issue) for r in view.field_reports):
            c = 1.0
        if view.containment and any(
            o.area == area and o.comms in ("backup", "down") for o in view.observed.areas
        ):
            c = max(c, CONTAINMENT_CONFIDENCE)  # a declared intrusion: lost supervision there is suspect
        return c

    def _score(self, coa: COA, view: AgentView) -> float:
        spec = ACTIONS[coa.action]
        intent, policy = self.intent_now, view.policy
        prio = 1.5 if intent and coa.target in intent.protect else 1.0
        tol = intent.risk_tolerance if intent else 0.2
        score = coa.benefit * prio - coa.risk * (1 - tol)
        if policy.prefer_reversible and spec.reversible:
            score += 0.2
        if policy.id == "C" and spec.weight in ("medium", "heavy"):
            score -= 0.1  # keep options open: prefer cheap measures first
        return score

    def _conflict_rank(self, action: str, policy_id: str) -> int:
        first, second = (SAFETY_FIRST, MISSION_FIRST) if policy_id == "B" else (MISSION_FIRST, SAFETY_FIRST)
        if action in first:
            return 0
        return 1 if action in second else 2

    def decide(
        self,
        view: AgentView,
        coas: list[COA],
        verdicts: dict[str, Verdict],
        vetoes: dict[str, str],
        advisor: Callable[[list[COA], int], set[str] | None] | None = None,
    ) -> list[Decision]:
        """Rules filter invalid, vetoed and low-confidence COAs and resolve conflicts. The final pick
        within attention is by score, or by `advisor` (an optional LLM, given only the eligible COAs)
        when it answers; any advisor failure falls back to the score."""
        policy, isr = view.policy, view.isr
        out: list[Decision] = []
        candidates: list[tuple[float, COA]] = []
        for coa in coas:
            v = verdicts[coa.key]
            if not v.ok:
                out.append(Decision(coa, False, f"invalid:{v.observable_code}", v))
                continue
            if coa.key in vetoes:
                out.append(Decision(coa, False, f"vetoed:{vetoes[coa.key]}", v))
                continue
            weight = ACTIONS[coa.action].weight
            if weight != "restore" and self.confidence(isr, coa, view) < policy.threshold(weight):
                out.append(Decision(coa, False, "below_threshold", v))
                continue
            candidates.append((self._score(coa, view), coa))
        candidates.sort(key=lambda sc: (-sc[0], sc[1].key))

        # conflicts on the same target: keep the one the policy ranks first
        kept: list[COA] = []
        lost: dict[str, str] = {}
        for _, coa in candidates:
            clash = next(
                (
                    k
                    for k in kept
                    if k.target == coa.target and frozenset({k.action, coa.action}) in CONFLICTS
                ),
                None,
            )
            if clash is None:
                kept.append(coa)
            elif self._conflict_rank(coa.action, policy.id) < self._conflict_rank(clash.action, policy.id):
                kept.remove(clash)
                kept.append(coa)
                lost[clash.key] = coa.key
            else:
                lost[coa.key] = clash.key

        capacity = int(view.available("operator_attention"))
        eligible = [coa for _, coa in candidates if coa.key not in lost]
        picks = advisor(eligible, capacity) if advisor and eligible and capacity > 0 else None
        if picks is not None:
            picks = {k for k in picks if k in {c.key for c in eligible}}
            picks = set(sorted(picks, key=[c.key for c in eligible].index)[:capacity])
        for _, coa in candidates:
            v = verdicts[coa.key]
            if coa.key in lost:
                out.append(Decision(coa, False, "conflict_lost", v, (lost[coa.key],)))
            elif picks is not None and coa.key not in picks:
                out.append(Decision(coa, False, "not_selected_by_c2", v))
            elif capacity <= 0:
                out.append(Decision(coa, False, "attention_saturated", v))
            else:
                conflicts = tuple(k for k, w in lost.items() if w == coa.key)
                out.append(Decision(coa, True, "approved", v, conflicts))
                capacity -= 1
        return out
