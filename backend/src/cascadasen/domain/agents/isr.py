"""ISR agent: builds the operational picture from incomplete, delayed and noisy evidence.

Per area it keeps a suspicion score (decaying) fed by alarms, missing or stale supervision and
field reports. An alarm that the values do not corroborate counts little (it may be false). The
cause belief (failure vs intentional) is a log-odds update with the likelihood ratios in
`theater.yaml` (isr). ISR may task extra monitoring and ask for field verification.
"""

from __future__ import annotations

import math

from cascadasen.domain.agents.base import AgentView
from cascadasen.domain.theater.areas import TheaterNetwork
from cascadasen.domain.theater.catalog import Role
from cascadasen.domain.theater.decisions import COA, ISRReport

DIGITAL = {
    "telemetry_lost": 0.6,
    "comms_lost": 0.6,
    "data_anomaly": 0.5,
    "control_lost": 0.5,
    "external_service": 0.3,
    "defense_fault": 0.4,
}
PHYSICAL = {
    "load_loss": 0.5,
    "blackout": 0.7,
    "breaker_open": 0.5,
    "frequency_event": 0.5,
    # graded physical alarms (docs/agents.md 1.4); voltage_limited is physical evidence, not intent
    "frequency_out_of_band": 0.4,
    "high_rocof": 0.3,
    "low_inertia": 0.2,
    "voltage_limited": 0.3,
}


def _logit(p: float) -> float:
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class ISRAgent:
    role = Role.ISR

    def __init__(self, network: TheaterNetwork, cfg: dict[str, float]) -> None:
        self.net, self.cfg = network, cfg
        self.suspicion = {a: 0.0 for a in network.order}
        self.digital_streak = {a: 0 for a in network.order}
        self.confirmed: dict[str, bool] = {}
        self.log_odds = _logit(cfg["prior_intentional"])
        self.report: ISRReport | None = None
        self.requested: dict[str, int] = {}  # area -> cycle of the last tasking request

    def _corroborated(self, view: AgentView, area: str, kind: str) -> bool:
        o = view.observed.area(area)
        if kind in ("load_loss", "blackout"):
            return o.energized is False or (o.served_mw is not None and o.served_mw < 0.97 * o.load_mw)
        if kind == "breaker_open":
            return any(
                st == "open" for cid, st in view.observed.corridors if area in cid.split("/")[0].split("-")
            )
        return True

    def step(self, view: AgentView) -> tuple[ISRReport, list[COA]]:
        """Update the ISR picture from this cycle's observation. Returns the report and the field-verification
        requests of `_requests`.

        1. Evidence per area. Each alarm adds the weight of its kind. A physical alarm counts in full only when
           `_corroborated` by the observed values (energized, served MW, open breakers), otherwise it adds 0.1.
           Stale data adds 0.1. A field report with an issue adds 0.8 and confirms the area. A clean field report
           resets the area's suspicion, evidence and confirmation.
        2. Suspicion = `decay` * previous suspicion + evidence, capped at 1.
        3. Cause belief, as log-odds of "intentional". Likelihood ratios from the config apply for digital alarms
           in two or more areas, a data-anomaly alarm, a field report that confirms a digital issue, physical
           alarms without digital ones, and a digital streak that reaches `corroboration_cycles`. With no alarms
           it drifts back to the prior. It is clamped to +-6.
        4. Report. An area is affected when its suspicion reaches `affected_threshold` or it is in outage. The
           leading cause is `none`, `intentional` (p >= 0.5) or `failure`. `verify` lists the unconfirmed areas
           with suspicion of at least 0.25 that are not in outage, most suspicious first. `data_trust` is 1 minus
           suspicion, and 0 where the served power is not observed."""
        cfg = self.cfg
        evidence = dict.fromkeys(self.net.order, 0.0)
        digital_areas, physical_areas, integrity = set(), set(), False
        for alarm in view.observed.alarms:
            a, k = alarm.area, alarm.kind
            if a not in evidence:
                continue
            if k in DIGITAL:
                evidence[a] += DIGITAL[k]
                digital_areas.add(a)
                integrity |= k == "data_anomaly"
            elif k in PHYSICAL:
                if self._corroborated(view, a, k):
                    evidence[a] += PHYSICAL[k]
                    physical_areas.add(a)
                else:
                    evidence[a] += 0.1
        for o in view.observed.areas:
            if o.age > 0:
                evidence[o.area] += 0.1
        field_digital = False
        for rep in view.field_reports:
            if rep.digital_issue or rep.physical_issue:
                evidence[rep.area] += 0.8
                self.confirmed[rep.area] = True
                field_digital |= rep.digital_issue and not rep.physical_issue
                if rep.digital_issue:
                    digital_areas.add(rep.area)
            else:
                self.suspicion[rep.area] = 0.0
                evidence[rep.area] = 0.0
                self.confirmed[rep.area] = False

        for a in self.net.order:
            self.suspicion[a] = min(1.0, cfg["decay"] * self.suspicion[a] + evidence[a])
            self.digital_streak[a] = self.digital_streak[a] + 1 if a in digital_areas else 0

        # cause belief
        if len(digital_areas) >= 2:
            self.log_odds += math.log(cfg["lr_multi_area_digital"])
        if integrity:
            self.log_odds += math.log(cfg["lr_unreliable_detected"])
        if field_digital:
            self.log_odds += math.log(cfg["lr_field_confirms_digital"])
        if physical_areas and not digital_areas:
            self.log_odds += math.log(cfg["lr_physical_only"])
        if any(s >= cfg["corroboration_cycles"] for s in self.digital_streak.values()):
            self.log_odds += math.log(cfg["lr_persistence"])
        if not digital_areas and not physical_areas:
            self.log_odds = 0.8 * self.log_odds + 0.2 * _logit(cfg["prior_intentional"])
        self.log_odds = max(-6.0, min(6.0, self.log_odds))
        p = _sigmoid(self.log_odds)

        outages = tuple(view.outages())
        affected = tuple(
            a for a in self.net.order if self.suspicion[a] >= cfg["affected_threshold"] or a in outages
        )
        if not affected:
            cause, confidence, key = "none", 1.0 - max(self.suspicion.values()), "isr_quiet"
        elif p >= 0.5:
            cause, confidence, key = "intentional", p, "isr_intentional_pattern"
        else:
            cause, confidence, key = "failure", 1 - p, "isr_failure_pattern"
        verify = tuple(
            sorted(
                (
                    a
                    for a in self.net.order
                    if self.suspicion[a] >= 0.25 and a not in self.confirmed and a not in outages
                ),
                key=lambda a: -self.suspicion[a],
            )
        )
        trust = tuple(
            (o.area, 0.0 if o.served_mw is None else round(max(0.0, 1.0 - self.suspicion[o.area]), 3))
            for o in view.observed.areas
        )
        self.report = ISRReport(
            cycle=view.cycle,
            p_intentional=p,
            leading_cause=cause,
            confidence=confidence,
            affected=affected,
            suspicion=tuple((a, round(s, 3)) for a, s in self.suspicion.items()),
            data_trust=trust,
            verify=verify,
            outages=outages,
            rationale_key=key,
        )
        return self.report, self._requests(view, verify)

    def _requests(self, view: AgentView, verify: tuple[str, ...]) -> list[COA]:
        coas = []
        slots = int(view.available("analyst_attention"))
        for a in sorted(self.net.order, key=lambda x: -self.suspicion[x]):
            if slots <= 0 or self.suspicion[a] < 0.3:
                break
            if view.cycle - self.requested.get(a, -99) >= 3:
                coas.append(COA("isr_tasking", a, Role.ISR.value, "isr_focus_area", benefit=0.4))
                self.requested[a] = view.cycle
                slots -= 1
        for a in verify[:2]:
            coas.append(COA("field_verification", a, Role.ISR.value, "isr_needs_ground_truth", benefit=0.6))
        return coas
