"""Island frequency model: one swing equation per island, with primary reserve, batteries, load damping and EDAC.

    (2*E / f0) * df/dt = P_gen + P_reserve + P_bat - P_curtailed - P_load(f)      E in MW*s, df/dt in Hz/s

E is the kinetic energy of the synchronous units online in the island (solar and wind add none); a unit that
trips before the transient is already out of E. Every number comes from `params/cascade.yaml` with a source or
`is_assumption` (docs/engine.md). Sources: docs/stack.md 4.4-4.5; EDAC from the CEN 25F report [4].
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cascadasen.domain.simulation.params import load_params, value

PARAMS_DIR = Path(__file__).parent / "params"


def cascade_params() -> dict[str, Any]:
    """The validated parameter tree of `params/cascade.yaml` (cached by the loader)."""
    return load_params("cascade", PARAMS_DIR)


_P = cascade_params()
_F, _E = _P["frequency"], _P["edac"]

F0 = float(value(_F["f0_hz"]))
BLACKOUT_LOW_HZ = float(value(_F["blackout_low_hz"]))
BLACKOUT_HIGH_HZ = float(value(_F["blackout_high_hz"]))
OVERFREQ_START_HZ = float(value(_F["overfrequency_curtailment"])["start_hz"])
OVERFREQ_SLOPE = float(value(_F["overfrequency_curtailment"])["share_per_hz"])

_CS = value(_E["centro_sur"])
CENTRO_SUR_STEPS_HZ: list[float] = [float(x) for x in _CS["steps_hz"]]
CENTRO_SUR_GRADIENT: list[bool] = [bool(x) for x in _CS["gradient"]]
CENTRO_SUR_ZONES: dict[str, list[tuple[float, float]]] = {
    zone: [(float(lo), float(hi)) for lo, hi in rows] for zone, rows in _CS["zones"].items()
}
NORTE_GRANDE_STEPS: list[tuple[float, float]] = [(float(t), float(mw)) for t, mw in value(_E["norte_grande"])]
GRADIENT_HZ_PER_S = float(value(_E["gradient_hz_s"]))
GRADIENT_MAX_HZ = float(value(_E["gradient_max_hz"]))
_LOW_DEMAND, _HIGH_DEMAND = float(value(_E["low_demand_mw"])), float(value(_E["high_demand_mw"]))
_MAX_STEP_SHARE = float(value(_E["max_step_share"]))


@dataclass(frozen=True)
class Params:
    load_damping_pct_per_hz: float = float(value(_F["load_damping_pct_per_hz"]))
    reserve_share_of_sync: float = float(value(_F["reserve_share_of_sync"]))
    reserve_droop: float = float(value(_F["reserve_droop"]))
    reserve_time_constant_s: float = float(value(_F["reserve_time_constant_s"]))
    battery_delay_s: float = float(value(_F["battery_delay_s"]))
    battery_ramp_s: float = float(value(_F["battery_ramp_s"]))
    battery_trigger_hz: float = float(value(_F["battery_trigger_hz"]))
    horizon_s: float = float(value(_F["horizon_s"]))
    step_s: float = float(value(_F["step_s"]))
    sample_every: int = int(value(_F["sample_every"]))


@dataclass(frozen=True)
class EdacStep:
    threshold_hz: float
    fraction: float  # share of the island's load in that zone that the step sheds
    gradient: bool


@dataclass
class IslandInput:
    inertia_mws: float
    sync_mw: float
    gen_mw: float
    load_mw: float
    nonsync_mw: float
    zone_load_mw: dict[str, float]
    edac: dict[str, list[EdacStep]]
    extra_reserve_mw: float = 0.0  # fast reserve committed to this island (strategic theatre), first order
    battery_mw: float = 0.0  # batteries in fast-frequency mode: delay then linear ramp


@dataclass
class IslandResult:
    outcome: str  # maintains | blackout
    min_hz: float
    final_hz: float
    collapse_t: float | None
    curve: list[list[float]]
    shed_mw: dict[str, float]
    steps: list[dict] = field(default_factory=list)
    reserve_mw: float = 0.0
    curtailed_mw: float = 0.0
    battery_mw: float = 0.0
    inertia_mws: float = 0.0
    rocof_hz_s: float = 0.0  # initial df/dt = f0 * dP / (2E)


def edac_tables(zone_load_mw: dict[str, float], system_load_mw: float) -> dict[str, list[EdacStep]]:
    """Each step's MW becomes a fraction of the zone's load at this operating point, so a smaller island sheds less."""
    weight = min(1.0, max(0.0, (system_load_mw - _LOW_DEMAND) / (_HIGH_DEMAND - _LOW_DEMAND)))
    steps = []
    for k, threshold in enumerate(CENTRO_SUR_STEPS_HZ):
        low = sum(rows[k][0] for rows in CENTRO_SUR_ZONES.values())
        high = sum(rows[k][1] for rows in CENTRO_SUR_ZONES.values())
        steps.append((threshold, low + weight * (high - low), CENTRO_SUR_GRADIENT[k]))
    cs_load = zone_load_mw.get("centro_sur", 0.0)
    return {
        "centro_sur": [_step(t, mw, cs_load, g) for t, mw, g in steps],
        "norte_grande": [
            _step(t, mw, zone_load_mw.get("norte_grande", 0.0), False) for t, mw in NORTE_GRANDE_STEPS
        ],
    }


def _step(threshold: float, mw: float, zone_load: float, gradient: bool) -> EdacStep:
    return EdacStep(threshold, min(_MAX_STEP_SHARE, mw / zone_load) if zone_load > 0 else 0.0, gradient)


def battery_output(t_since_trigger: float | None, p_max: float, params: Params) -> float:
    """Battery injection: nothing during the delay, then a linear ramp to full power (stack.md 4.5)."""
    if p_max <= 0 or t_since_trigger is None or t_since_trigger <= params.battery_delay_s:
        return 0.0
    return min(p_max, p_max * (t_since_trigger - params.battery_delay_s) / params.battery_ramp_s)


def simulate_island(island: IslandInput, params: Params = Params()) -> IslandResult:
    f, reserve, shed, dfdt = F0, 0.0, {z: 0.0 for z in island.zone_load_mw}, 0.0
    done: set[tuple[str, int]] = set()
    steps_log: list[dict] = []
    curve: list[list[float]] = []
    cap = params.reserve_share_of_sync * island.sync_mw + island.extra_reserve_mw
    gain = island.sync_mw / (params.reserve_droop * F0) if params.reserve_droop > 0 else float("inf")
    min_hz, collapse, rocof, bat_t0, bat = F0, None, 0.0, None, 0.0
    for k in range(int(params.horizon_s / params.step_s) + 1):
        t = k * params.step_s
        if k % params.sample_every == 0:
            curve.append([round(t, 2), round(f, 3)])
        target = _clamp((F0 - f) * gain, -cap, cap) if cap > 0 else 0.0
        reserve += (target - reserve) / params.reserve_time_constant_s * params.step_s
        if bat_t0 is None and f < params.battery_trigger_hz:
            bat_t0 = t
        bat = battery_output(None if bat_t0 is None else t - bat_t0, island.battery_mw, params)
        curtailed = min(
            island.nonsync_mw, OVERFREQ_SLOPE * island.nonsync_mw * max(0.0, f - OVERFREQ_START_HZ)
        )
        load = (island.load_mw - sum(shed.values())) * (1 + params.load_damping_pct_per_hz / 100 * (f - F0))
        dfdt = F0 * (island.gen_mw + reserve + bat - curtailed - load) / (2 * island.inertia_mws)
        if k == 0:
            rocof = dfdt
        f += dfdt * params.step_s
        min_hz = min(min_hz, f)
        _trigger_edac(island, f, dfdt, t, shed, done, steps_log)
        if f < BLACKOUT_LOW_HZ or f > BLACKOUT_HIGH_HZ:
            collapse = t
            break
    outcome = "blackout" if collapse is not None else "maintains"
    return IslandResult(
        outcome,
        round(min_hz, 3),
        round(f, 3),
        collapse,
        curve,
        shed,
        steps_log,
        reserve,
        curtailed,
        bat,
        island.inertia_mws,
        round(rocof, 3),
    )


def _trigger_edac(
    island: IslandInput, f: float, dfdt: float, t: float, shed: dict, done: set, log: list
) -> None:
    for zone, steps in island.edac.items():
        for j, step in enumerate(steps):
            hit = f <= step.threshold_hz or (
                step.gradient and dfdt <= GRADIENT_HZ_PER_S and f < GRADIENT_MAX_HZ
            )
            if hit and (zone, j) not in done:
                done.add((zone, j))
                mw = step.fraction * island.zone_load_mw.get(zone, 0.0)
                shed[zone] = shed.get(zone, 0.0) + mw
                if mw >= 0.5:  # steps with nothing to shed in this island stay out of the narration
                    log.append({"t": round(t, 2), "zone": zone, "step": j + 1, "mw": round(mw, 1)})


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
