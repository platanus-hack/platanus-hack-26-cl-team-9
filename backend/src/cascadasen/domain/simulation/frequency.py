"""Island frequency model: aggregated swing equation (docs/stack.md 4.4 and 4.5).

    (2 E / f0) df/dt = P_gen + P_link(t) - P_lost(t) + P_reserve + P_bat - P_load + P_shed - P_curt - dP_load(f)
    dP_load(f) = D/100 * P_load * (f - f0)

E is the island kinetic energy in MW·s. Couplings carry the pre-event flow of a corridor that
separates later (the weak link) until its trip time. Ramps model generation that disconnects
progressively (the "as it happened" 25F mode).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cascadasen.domain.simulation.defenses import DefenseSet
from cascadasen.domain.simulation.grid import Physics


@dataclass(frozen=True)
class Coupling:
    corridor: str
    t_trip: float
    inflow_mw: float


@dataclass(frozen=True)
class Ramp:
    start: float
    end: float
    mw: float
    label_key: str

    def lost(self, t: float) -> float:
        if t <= self.start:
            return 0.0
        if t >= self.end or self.end <= self.start:
            return self.mw
        return self.mw * (t - self.start) / (self.end - self.start)


@dataclass
class IslandInput:
    id: str
    areas: list[str]
    gen_mw: float
    sync_mw: float
    nonsync_mw: float
    load_mw: float
    kinetic_mws: float
    reserve_mw: float
    battery_mw: float
    couplings: list[Coupling] = field(default_factory=list)
    ramps: list[Ramp] = field(default_factory=list)
    edac_share: float = 1.0
    extreme_mw: float = 0.0
    lfsm: bool = True
    h_trip_s: float = 0.0


@dataclass
class ShedEvent:
    t: float
    mw: float
    label_key: str
    step: int


@dataclass
class IslandTrace:
    id: str
    result: str  # maintains | blackout | local_cut | no_load
    f_min: float
    f_max: float
    t_f_min: float
    f_end: float | None
    rocof_initial: float
    blackout_t: float | None = None
    shed_mw: float = 0.0
    curtailed_mw: float = 0.0
    lost_mw: float = 0.0
    reserve_mw: float = 0.0
    battery_mw: float = 0.0
    shed_events: list[ShedEvent] = field(default_factory=list)
    samples: list[tuple[float, float]] = field(default_factory=list)


def _battery(t: float, p_max: float, physics: Physics) -> float:
    if p_max <= 0 or t <= physics.battery_delay:
        return 0.0
    return min(p_max, p_max * (t - physics.battery_delay) / physics.battery_ramp)


def steady_trace(island: IslandInput, physics: Physics, full: bool) -> IslandTrace:
    """An island with no disturbance: frequency stays at nominal."""
    samples = []
    if full:
        n = round(physics.horizon / physics.frame_step)
        samples = [(round(k * physics.frame_step, 3), physics.f0) for k in range(n + 1)]
    return IslandTrace(island.id, "maintains", physics.f0, physics.f0, 0.0, physics.f0, 0.0, samples=samples)


def simulate_island(
    island: IslandInput, defenses: DefenseSet, physics: Physics, full: bool = True
) -> IslandTrace:
    """Integrate the swing equation of one island and return its `IslandTrace`.

    Early exits: a load under 1 MW is `no_load`. An island with no synchronous kinetic energy is `local_cut`
    when its load is at most `local_cut_mw`, else `blackout` at t = 0. Otherwise it uses explicit Euler steps
    of `physics.dt` over the horizon, with df/dt = f0 * imbalance / (2 * E). E is the kinetic energy minus the
    inertia that the lost generation takes with it, never below 5 %. The imbalance adds generation, coupling
    inflow until each coupling trips, primary reserve and batteries, and subtracts load, lost ramps,
    curtailment (LFSM) and the frequency damping of the load that is left.

    Defences act on the current frequency. EDAC steps and the extreme-gradient shedding are queued with
    `edac_delay_s` and applied when due, capped by the island's load. LFSM curtails non-synchronous output
    above `lfsm_start_hz`. The reserve follows the frequency deviation with time constant `reserve_tau`. A
    frequency outside `blackout_hz` and `overfrequency_hz` ends the run as `blackout`, with no final
    frequency. With `full=False` the loop also stops once the events are over, |df/dt| is under 0.002 Hz/s
    and nothing is pending."""
    f0 = physics.f0
    if island.load_mw < 1.0:
        return IslandTrace(island.id, "no_load", f0, f0, 0.0, None, 0.0)
    if island.kinetic_mws <= 0 or island.sync_mw <= 0:
        result = "local_cut" if island.load_mw <= physics.local_cut_mw else "blackout"
        return IslandTrace(island.id, result, 0.0, f0, 0.0, None, 0.0, blackout_t=0.0, lost_mw=island.load_mw)

    h_trip = island.h_trip_s or island.kinetic_mws / island.sync_mw
    events_end = max([0.0, *(c.t_trip for c in island.couplings), *(r.end for r in island.ramps)])
    steps = round(physics.horizon / physics.dt)
    every = max(1, round(physics.frame_step / physics.dt))
    f, p_res, curt, shed = f0, 0.0, 0.0, 0.0
    fired: set[str] = set()
    pending: list[ShedEvent] = []
    trace = IslandTrace(island.id, "maintains", f0, f0, 0.0, f0, 0.0)
    shed_cap = island.load_mw
    for k in range(steps + 1):
        t = k * physics.dt
        link = sum(c.inflow_mw for c in island.couplings if t < c.t_trip)
        lost = sum(r.lost(t) for r in island.ramps)
        e = max(island.kinetic_mws - h_trip * lost, 0.05 * island.kinetic_mws)
        bat = _battery(t, island.battery_mw, physics)
        damping = physics.damping_pct_per_hz / 100.0 * (island.load_mw - shed) * (f - f0)
        imbalance = island.gen_mw - island.load_mw + link - lost + p_res + bat + shed - curt - damping
        dfdt = f0 * imbalance / (2.0 * e)
        if k == 1:
            trace.rocof_initial = round(dfdt, 3)
        if k % every == 0:
            trace.samples.append((round(t, 3), round(f, 4)))
        if f < trace.f_min:
            trace.f_min, trace.t_f_min = f, t
        trace.f_max = max(trace.f_max, f)

        # automatic defences, decided on the current frequency
        if island.edac_share > 0:
            for i, (hz, share) in enumerate(defenses.edac_steps):
                key = f"edac{i}"
                if key not in fired and f < hz:
                    fired.add(key)
                    mw = share * island.load_mw * island.edac_share
                    pending.append(ShedEvent(t + defenses.edac_delay_s, mw, "edac_step", i + 1))
        if island.extreme_mw > 0 and f < defenses.extreme_threshold_hz:
            for i, g in enumerate(defenses.extreme_gradients):
                key = f"ext{i}"
                if key not in fired and dfdt <= g:
                    fired.add(key)
                    mw = island.extreme_mw / len(defenses.extreme_gradients)
                    pending.append(ShedEvent(t + defenses.edac_delay_s, mw, "extreme_edac", i + 1))
        for ev in [p for p in pending if p.t <= t + 1e-9]:
            pending.remove(ev)
            mw = min(ev.mw, shed_cap - shed)
            if mw > 0:
                shed += mw
                trace.shed_events.append(ShedEvent(round(ev.t, 3), round(mw, 1), ev.label_key, ev.step))
        if island.lfsm and island.nonsync_mw > 0:
            target = 0.0
            if f > defenses.lfsm_start_hz:
                target = min(
                    island.nonsync_mw,
                    island.nonsync_mw * defenses.lfsm_share_per_hz * (f - defenses.lfsm_start_hz),
                )
            curt += (target - curt) * physics.dt / defenses.lfsm_tau_s
        dev = max(-1.0, min(1.0, (f0 - f) / physics.reserve_full_dev))
        p_res += (island.reserve_mw * dev - p_res) * physics.dt / physics.reserve_tau

        f += dfdt * physics.dt
        if f < physics.blackout_hz or f > physics.overfrequency_hz:
            trace.result, trace.blackout_t = "blackout", round(t, 3)
            trace.f_min = min(trace.f_min, f)
            trace.f_max = max(trace.f_max, f)
            trace.f_end = None
            trace.samples.append((round(t + physics.dt, 3), round(f, 4)))
            break
        if not full and t > events_end + 3.0 and abs(dfdt) < 0.002 and not pending:
            break
    if trace.result != "blackout":
        trace.f_end = round(f, 4)
    trace.f_min, trace.f_max = round(trace.f_min, 4), round(trace.f_max, 4)
    trace.t_f_min = round(trace.t_f_min, 3)
    trace.shed_mw = round(shed, 1)
    trace.curtailed_mw = round(curt, 1)
    trace.lost_mw = round(sum(r.mw for r in island.ramps), 1)
    trace.reserve_mw = round(p_res, 1)
    trace.battery_mw = round(_battery(physics.horizon, island.battery_mw, physics), 1)
    return trace
