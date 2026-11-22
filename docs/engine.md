# Cascade engine

Viewer guide and actor reference: [`mapa3.md`](mapa3.md). Minimum dataset and cut propagation: [`minimum-dataset.md`](minimum-dataset.md).

Status: implemented in `backend/src/cascadasen/domain/cascade/`, unit tests in `backend/tests/unit/test_cascade.py`. It follows `stack.md` section 4 with one change: the network is the 188-bus reduction of PyPSA-CL, not 10-14 aggregated nodes.

Two engines exist. This one (188 buses) drives the map's cached cuts and the strategic theatre with its agents (`strategy.md`, `agents.md`). The 13-area engine in `domain/simulation/` serves only `POST /api/v1/simulate` and its validation cases V1-V10.

Parameters live in `domain/cascade/params/cascade.yaml`. Every number carries a `source` or `is_assumption: true`; the loader of `domain/simulation/params.py` rejects bare numbers.

## What it does

Click a line, get the consequences: islands, load shed, people in the dark and the frequency of each island.

1. **Reduced network** (`network.py`): one bus per substation, transformers folded away, parallel lines merged (capacity added, reactance in parallel). 188 buses, 273 lines in 2025 and 2026. Links built after the point's year are left out (two 2029 links, one of them the Kimal-Lo Aguirre HVDC). Reactances below 5e-4 pu are raised to that value (assumption, keeps the solver well conditioned).
2. **Operating point** (`scenario.py`): load from PyPSA-CL `Loads.xlsx`, generation and inertia from the secure base case `data/processed/baseline_opf.json`, people from the INE comunas served by each node.
3. **Secure base case** (`data/scripts/build_baseline_opf.py`): DC optimal power flow (HiGHS) on the same reduced network, every line at or below 100% of its capacity (NTSyCS art. 5-27), inertia floor of 31,000 MWs. N-1 is **not** imposed: 10 to 21 lines sit at their limit.
4. **Cascade** (`engine.py`): open the cut, split into islands, settle each island (frequency model), DC flow, open the most overloaded line above 120% of capacity, repeat up to 20 stages.
5. **Island frequency** (`frequency.py`): `df/dt = f0 * dP / (2E)`, 10 ms step, 20 s horizon, with:
   - E = kinetic energy of the synchronous units online in the island. Solar and wind add none, so a midday point has less inertia (Nov 2026: 26.1 GVAs at 13:00 vs 36.4 GVAs at 20:00). A unit tripped before the transient is already out of E.
   - primary reserve with a 5% droop, capped at 4% of online synchronous MW, time constant 3 s; deployed reserve stays on synchronous units;
   - batteries in fast-frequency mode (theatre `battery_support`): start when f < 49.8 Hz, 200 ms delay, 300 ms ramp (`stack.md` 4.5);
   - load damping 1.5 %/Hz and over-frequency curtailment of solar and wind;
   - EDAC with the real steps (centro-sur table and norte grande Table 3-9 of the CEN 25F report). The extreme-contingency EDAC (671.55 MW by df/dt, [4] Tables 3-10/3-11) is not modelled: on its own it kept the centro-sur island above 47.5 Hz in the 25F, which the real system did not do, because the model has no voltage collapse or generator trips (removed 2026-11-22).
   Blackout below 47.5 Hz. Each island reports `min_hz`, `final_hz`, `rocof_hz_s` (initial df/dt), `inertia_mws`, `shed_mw` and `battery_mw`.
6. **Voltage collapse, a rule** (`engine.py`, `stack.md` 4.6): the DC model has no voltage. When the 25F corridor separates (its two ends, Nueva Maitencillo and Nueva Pan de Azúcar, end up in different islands) with a pre-fault flow above 1,600 MW N→S or 1,000 MW S→N, both islands collapse by voltage: `island_blackout` with `reason: "voltage"`, and the island in `summary.islands` carries `reason: "voltage"`. It is the only corridor with published limits. The health index marks that report uncertain (a rule, not a calculation). There is no `voltage_limited` result or `summary.uncertain` any more.

**25F check (V1 on this network, not hand-tuned):** at Feb 2025 15:00 the pre-fault DC flow is 1,905 MW on the 500 kV line and 287 MW on 220 kV (targets 1,800 and 314 MW, ±15%). Reactances are PyPSA-CL values, not calibrated; they are not real line data either.

## Run

```bash
cd backend
uv run cascadasen-cache            # writes web/public/cache/ (about 23 MB, 4 hours x 273 cuts)
uv run pytest tests/unit/test_cascade.py
```

The data scripts need the PyPSA-CL files in `data/raw/pypsa_cl/` (they download them): `build_operating_points.py`, then `build_baseline_opf.py` (needs `scipy`).

## Results so far (reduced network, base cases of `baseline_opf.json`)

| Hour | Cuts with no effect (of 273) | 25F corridor cut |
|---|---|---|
| Feb 2025 15:00 | 217 | 16.8 M people, 11,096 of 11,096 MW, 2 stages, both islands collapse by voltage at 2.0 s |
| Feb 2025 03:00 | 231 | 0.3 M people, 631 of 8,719 MW (corridor S→N under 1,000 MW: no voltage collapse) |
| Nov 2026 13:00 | 204 | 17.0 M people, 10,836 of 10,836 MW, 2 stages, voltage collapse |
| Nov 2026 20:00 | 213 | 3.9 M people, 1,825 of 10,934 MW (1,287 MW N→S, under the limit) |

Measured 2026-11-22. The real 25F left about 19 M people (98.5 %) without power (figure given by the team, source to cite). The model reaches 16.8 M because it assigns 18.16 M people in total and 23 substations over 20 MW have 0 people (`docs/minimum-dataset.md`). The corridor result depends on how loaded it was: that matches the CEN account of the 25F. Do not present these numbers as a forecast. A health index built on these results is in [`health.md`](health.md).

## Assumptions (also returned in every timeline)

See `ASSUMPTIONS` in `engine.py` and the `is_assumption` entries of `cascade.yaml`. The ones that matter most: the 120% opening threshold, 1 s between stages (illustrative), reserve 4% of online synchronous MW with 5% droop, load damping 1.5 %/Hz, no generation ride-through trips, flow DC without voltage. A click on a map line cuts the whole reduced line: where several circuits run in parallel (for example the four 500 kV circuits Alto Jahuel-Ancoa) that is the whole corridor, not one circuit.

## Not done

N-1 base case, the 25F scripted events (220 kV opening at 1.5 s; the north's voltage collapse stays documented, not computed), ride-through trips, battery energy limits, calibration of the island frequency against the CEN 25F numbers (V2 to V9 in `plan.md`; only the V1 flow split is checked on this network). The 13-area engine keeps those cases.
