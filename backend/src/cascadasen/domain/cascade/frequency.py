"""Island frequency model: one swing equation per island, with primary reserve, load damping and EDAC.

    (2*E / f0) * df/dt = P_gen + P_reserve - P_curtailed - P_load(f)        E in MW*s, df/dt in Hz/s

Sources: docs/stack.md 4.4; EDAC steps from the CEN 25F report (Tabla 3-9 and the centro-sur table, pag. 26-27);
over-frequency reduction from NTSyCS (55% of available power per Hz above 50.2 Hz).
"""

from __future__ import annotations

from dataclasses import dataclass, field

F0 = 50.0
BLACKOUT_LOW_HZ = 47.5     # NTSyCS art. 3-10 per the CEN 25F report
BLACKOUT_HIGH_HZ = 52.0    # assumption: above this the island trips
OVERFREQ_START_HZ, OVERFREQ_SLOPE = 50.2, 0.55

# Centro-sur EDAC by under-frequency: MW per zone and step as (low demand, high demand). CEN 25F report, centro-sur table.
CENTRO_SUR_STEPS_HZ = [49.0, 48.9, 48.8, 48.7, 48.5, 48.3]
CENTRO_SUR_GRADIENT = [True, False, True, False, False, False]   # steps 1 and 3 also act at -0.6 Hz/s
CENTRO_SUR_ZONES = {
    "Atacama": [(10, 22), (23, 13), (10, 19), (16, 23), (12, 26), (2, 1)],
    "Coquimbo": [(16, 40), (18, 23), (15, 34), (9, 11), (3, 18), (1, 2)],
    "Quinta Región": [(21, 56), (23, 22), (37, 48), (19, 12), (34, 23), (8, 10)],
    "Metropolitana": [(65, 207), (61, 142), (42, 170), (75, 143), (104, 145), (58, 117)],
    "Troncal Centro": [(9, 10), (2, 8), (7, 12), (8, 8), (3, 7), (1, 6)],
    "Sistema 154-66 kV": [(26, 74), (28, 49), (52, 88), (28, 21), (11, 18), (9, 19)],
    "Charrúa": [(16, 53), (5, 4), (15, 10), (11, 13), (12, 39), (2, 7)],
    "Concepción": [(65, 57), (17, 17), (27, 46), (14, 30), (12, 9), (7, 8)],
    "Araucanía": [(11, 30), (7, 9), (24, 46), (9, 16), (2, 8), (14, 8)],
}
# Norte grande EDAC (Tabla 3-9): step 1 at 49.0 Hz is disabled; MW assigned per step.
NORTE_GRANDE_STEPS = [(48.9, 52.0), (48.8, 102.9), (48.7, 90.9), (48.6, 104.8), (48.5, 117.9), (48.4, 119.7), (48.3, 119.2)]
GRADIENT_HZ_PER_S = -0.6
GRADIENT_MAX_HZ = 49.5   # assumption: the gradient trigger only counts below this frequency


@dataclass(frozen=True)
class Params:
    load_damping_pct_per_hz: float = 1.5     # assumption, 1-2 %/Hz (docs/stack.md 4.4)
    reserve_share_of_sync: float = 0.04      # assumption: primary reserve = 4% of online synchronous MW
    reserve_full_at_hz: float = 0.3          # assumption: full reserve at 0.3 Hz deviation
    reserve_time_constant_s: float = 3.0     # assumption
    horizon_s: float = 20.0
    step_s: float = 0.01
    sample_every: int = 20                   # 5 Hz curve


@dataclass(frozen=True)
class EdacStep:
    threshold_hz: float
    fraction: float       # share of the island's load in that zone that the step sheds
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


@dataclass
class IslandResult:
    outcome: str                      # maintains | blackout
    min_hz: float
    final_hz: float
    collapse_t: float | None
    curve: list[list[float]]
    shed_mw: dict[str, float]
    steps: list[dict] = field(default_factory=list)
    reserve_mw: float = 0.0
    curtailed_mw: float = 0.0


def edac_tables(zone_load_mw: dict[str, float], system_load_mw: float) -> dict[str, list[EdacStep]]:
    """Each step's MW becomes a fraction of the zone's load at this operating point, so a smaller island sheds less."""
    weight = min(1.0, max(0.0, (system_load_mw - 8500.0) / 3000.0))  # assumption: 8.5 GW = low demand, 11.5 GW = high demand
    steps = []
    for k, threshold in enumerate(CENTRO_SUR_STEPS_HZ):
        low = sum(rows[k][0] for rows in CENTRO_SUR_ZONES.values())
        high = sum(rows[k][1] for rows in CENTRO_SUR_ZONES.values())
        steps.append((threshold, low + weight * (high - low), CENTRO_SUR_GRADIENT[k]))
    return {
        "centro_sur": [_step(t, mw, zone_load_mw.get("centro_sur", 0.0), g) for t, mw, g in steps],
        "norte_grande": [_step(t, mw, zone_load_mw.get("norte_grande", 0.0), False) for t, mw in NORTE_GRANDE_STEPS],
    }


def _step(threshold: float, mw: float, zone_load: float, gradient: bool) -> EdacStep:
    return EdacStep(threshold, min(0.5, mw / zone_load) if zone_load > 0 else 0.0, gradient)


def simulate_island(island: IslandInput, params: Params = Params()) -> IslandResult:
    f, reserve, shed, dfdt = F0, 0.0, {z: 0.0 for z in island.zone_load_mw}, 0.0
    done: set[tuple[str, int]] = set()
    steps_log: list[dict] = []
    curve: list[list[float]] = []
    cap = params.reserve_share_of_sync * island.sync_mw
    min_hz, collapse = F0, None
    for k in range(int(params.horizon_s / params.step_s) + 1):
        t = k * params.step_s
        if k % params.sample_every == 0:
            curve.append([round(t, 2), round(f, 3)])
        reserve += (_clamp((F0 - f) / params.reserve_full_at_hz, -1, 1) * cap - reserve) / params.reserve_time_constant_s * params.step_s
        curtailed = min(island.nonsync_mw, OVERFREQ_SLOPE * island.nonsync_mw * max(0.0, f - OVERFREQ_START_HZ))
        load = (island.load_mw - sum(shed.values())) * (1 + params.load_damping_pct_per_hz / 100 * (f - F0))
        dfdt = F0 * (island.gen_mw + reserve - curtailed - load) / (2 * island.inertia_mws)
        f += dfdt * params.step_s
        min_hz = min(min_hz, f)
        _trigger_edac(island, f, dfdt, t, shed, done, steps_log)
        if f < BLACKOUT_LOW_HZ or f > BLACKOUT_HIGH_HZ:
            collapse = t
            break
    outcome = "blackout" if collapse is not None else "maintains"
    return IslandResult(outcome, round(min_hz, 3), round(f, 3), collapse, curve, shed, steps_log, reserve, curtailed)


def _trigger_edac(island: IslandInput, f: float, dfdt: float, t: float, shed: dict, done: set, log: list) -> None:
    for zone, steps in island.edac.items():
        for j, step in enumerate(steps):
            hit = f <= step.threshold_hz or (step.gradient and dfdt <= GRADIENT_HZ_PER_S and f < GRADIENT_MAX_HZ)
            if hit and (zone, j) not in done:
                done.add((zone, j))
                mw = step.fraction * island.zone_load_mw.get(zone, 0.0)
                shed[zone] = shed.get(zone, 0.0) + mw
                if mw >= 0.5:  # steps with nothing to shed in this island stay out of the narration
                    log.append({"t": round(t, 2), "zone": zone, "step": j + 1, "mw": round(mw, 1)})


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
