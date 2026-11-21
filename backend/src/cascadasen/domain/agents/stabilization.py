"""Stabilisation agent: protects physical constraints and prioritises continuity and safe recovery.

It reasons on its own estimate of the grid (the day-ahead plan corrected by what supervision shows),
never on the real grid. Its physical contract is in docs/agents.md: the operating band (49.0-51.0 Hz),
a steep initial RoCoF, an island that lost inertia, and islands whose verdict is voltage-limited
(uncertain: voltage is documented, not computed).

- Fast response (batteries) when RoCoF is steep or inertia was lost: they act in half a second.
- Reserve when frequency stays out of band after the transient, or after load shedding.
- Load reduction when an island stays under-frequency and no reserve or battery is left.
- Vetoes restorations while an island is out of band, still swinging or voltage-uncertain, and a
  controlled islanding next to an island that lost inertia.
"""

from __future__ import annotations

from cascadasen.domain.agents.base import AgentView
from cascadasen.domain.theater.areas import TheaterNetwork
from cascadasen.domain.theater.catalog import Role
from cascadasen.domain.theater.config import theater_config
from cascadasen.domain.theater.decisions import COA

STAB = Role.STAB.value
FAST_POOL_MW = 100.0  # one battery or reserve block (theater.yaml actions)


class StabilizationAgent:
    role = Role.STAB

    def __init__(
        self, network: TheaterNetwork, plan_load: dict[str, float], defense_areas: dict[str, list[str]]
    ):
        self.net = network
        self.plan = dict(plan_load)
        self.defense_areas = defense_areas
        self.unstable_until = -1
        band = theater_config().physics_alarms
        self.band = (band.get("band_low_hz", 49.0), band.get("band_high_hz", 51.0))
        self.out_of_band: set[str] = set()  # estimate: areas whose island is outside the band
        self.voltage_until: dict[str, int] = {}  # area -> last cycle its island stays voltage-uncertain
        self.low_inertia: set[str] = set()
        self._corridors: tuple[tuple[str, str | None], ...] = ()

    def _defense_for(self, area: str) -> str | None:
        for did, areas in self.defense_areas.items():
            if did.startswith("edac:") or did == "pdce_zn":
                if area in areas:
                    return did
        return None

    def _estimate(self, view: AgentView) -> tuple[bool, set[str], set[str]]:
        """Update the physical estimate from this cycle's feed. Returns (shed or collapse seen, areas
        needing fast response, areas under-frequency)."""
        obs = view.observed
        lo, hi = self.band
        self._corridors = obs.corridors
        kinds: dict[str, set[str]] = {}
        for alarm in obs.alarms:
            kinds.setdefault(alarm.kind, set()).add(alarm.area)
        frequency = bool(kinds.get("frequency_event"))
        if frequency:
            self.unstable_until = view.cycle + 1
        under = {o.area for o in obs.areas if o.freq_hz is not None and o.freq_hz < lo}
        over = {o.area for o in obs.areas if o.freq_hz is not None and o.freq_hz > hi}
        self.out_of_band = kinds.get("frequency_out_of_band", set()) | under | over
        for a in kinds.get("voltage_limited", set()):
            for x in self._island_areas(a):
                self.voltage_until[x] = view.cycle + 1
        self.low_inertia = kinds.get("low_inertia", set())
        fast = kinds.get("high_rocof", set()) | self.low_inertia
        return frequency, fast, under

    def _island_areas(self, area: str) -> list[str]:
        """The area plus its neighbours through corridors seen closed: its island, as far as supervision tells."""
        seen, todo = {area}, [area]
        closed = [self.net.corridors[cid] for cid, st in self._corridors if st == "closed"]
        while todo:
            a = todo.pop()
            for c in closed:
                for x, y in ((c.a, c.b), (c.b, c.a)):
                    if x == a and y not in seen:
                        seen.add(y)
                        todo.append(y)
        return sorted(seen)

    def propose(self, view: AgentView) -> list[COA]:
        obs, isr, intent, policy = view.observed, view.isr, view.intent, view.policy
        active = set(view.active)
        coas: list[COA] = []

        def add(action: str, target: str, key: str, benefit: float, risk: float = 0.0) -> None:
            if f"{action}:{target}" not in active and not any(c.action == action for c in coas):
                coas.append(COA(action, target, STAB, key, benefit=benefit, risk=risk))

        frequency, fast, under = self._estimate(view)
        escalation = intent.escalation if intent else 0
        protect = [a for a in (intent.protect if intent else ()) if a in self.net.areas]
        preemptive = (policy.preventive and escalation >= 1) or (policy.id == "C" and escalation >= 2)

        def energized(a: str) -> bool:
            return obs.area(a).energized is not False

        # fast response where the RoCoF is steep or inertia was lost, priority areas first
        for a in [x for x in protect if x in fast] + sorted(fast - set(protect)):
            if energized(a) and view.available("battery_mw") >= FAST_POOL_MW:
                add("battery_support", a, "stab_fast_support_low_inertia", 0.7)
                break
        # reserve where frequency stayed out of band, then the priority areas after a shed or collapse
        if under or frequency or preemptive:
            for a in sorted(under) + protect:
                if not energized(a):
                    continue
                if (frequency or preemptive) and view.available("battery_mw") >= FAST_POOL_MW:
                    add("battery_support", a, "stab_fast_support_priority_area", 0.6)
                if view.available("fast_reserve_mw") >= FAST_POOL_MW:
                    key = "stab_reserve_under_frequency" if a in under else "stab_reserve_priority_area"
                    add("fast_reserve", a, key, 0.6 if a in under else 0.5)
                break
        for alarm in obs.alarms:
            if alarm.kind == "defense_fault":
                did = self._defense_for(alarm.area)
                if did:
                    add("rearm_defense", did, "stab_rearm_defense", 0.9)
        no_fast = (
            view.available("fast_reserve_mw") < FAST_POOL_MW and view.available("battery_mw") < FAST_POOL_MW
        )
        shed_candidates = [a for a in sorted(under) if a not in protect and energized(a)]
        if under and no_fast and shed_candidates:
            add("preventive_load_reduction", shed_candidates[0], "stab_preventive_margin", 0.5, 0.2)
        elif policy.preventive and escalation >= 2 and isr:
            candidates = [a for a in isr.affected if a not in protect and a not in isr.outages]
            if candidates:
                add("preventive_load_reduction", candidates[0], "stab_preventive_margin", 0.4, 0.2)
        return coas

    def review(self, view: AgentView, coas: list[COA]) -> dict[str, str]:
        """Vetoes on its own estimate: no restoration into an island that is still swinging, out of band or
        voltage-uncertain; no controlled islanding next to an island that lost inertia."""
        vetoes: dict[str, str] = {}
        voltage = {a for a, until in self.voltage_until.items() if view.cycle <= until}
        for c in coas:
            if c.action == "restore_element":
                if c.target in self.net.areas:
                    areas = [c.target]
                elif c.target in self.net.corridors:
                    areas = [self.net.corridors[c.target].a, self.net.corridors[c.target].b]
                else:
                    continue
                if any(a in voltage for a in areas):
                    vetoes[c.key] = "stab_voltage_uncertain"
                elif c.target in self.net.areas and (
                    view.cycle <= self.unstable_until or c.target in self.out_of_band
                ):
                    vetoes[c.key] = "stab_wait_for_stability"
            elif c.action == "islanding_prep" and c.target in self.net.corridors:
                cor = self.net.corridors[c.target]
                if cor.a in self.low_inertia or cor.b in self.low_inertia:
                    vetoes[c.key] = "stab_low_inertia"
        return vetoes
