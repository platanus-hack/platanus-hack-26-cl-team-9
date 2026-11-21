# Cascade engine

Viewer guide and actor reference: [`mapa3.md`](mapa3.md).

Status: implemented in `backend/src/cascadasen/domain/cascade/`, 11 unit tests in `backend/tests/unit/test_cascade.py`. It follows `stack.md` section 4 with one change: the network is the 188-bus reduction of PyPSA-CL, not 10-14 aggregated nodes.

## What it does

Click a line, get the consequences: islands, load shed, people in the dark and the frequency of each island.

1. **Reduced network** (`network.py`): one bus per substation, transformers folded away, parallel lines merged (capacity added, reactance in parallel). 188 buses, 273 lines in 2025 and 2026. Links built after the point's year are left out (two 2029 links, one of them the Kimal-Lo Aguirre HVDC). Reactances below 5e-4 pu are raised to that value (assumption, keeps the solver well conditioned).
2. **Operating point** (`scenario.py`): load from PyPSA-CL `Loads.xlsx`, generation and inertia from the secure base case `data/processed/baseline_opf.json`, people from the INE comunas served by each node.
3. **Secure base case** (`data/scripts/build_baseline_opf.py`): DC optimal power flow (HiGHS) on the same reduced network, every line at or below 100% of its capacity (NTSyCS art. 5-27), inertia floor of 31,000 MWs. N-1 is **not** imposed: 10 to 21 lines sit at their limit.
4. **Cascade** (`engine.py`): open the cut, split into islands, settle each island (frequency model), DC flow, open the most overloaded line above 120% of capacity, repeat up to 20 stages.
5. **Island frequency** (`frequency.py`): `df/dt = f0 * dP / (2E)` with primary reserve, load damping, over-frequency curtailment of solar and wind, and EDAC with the real steps (centro-sur table and norte grande Tabla 3-9 of the CEN 25F report). Blackout below 47.5 Hz.

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
| Feb 2025 15:00 | 227 | 15.2 M people, 7,872 of 11,096 MW, 2 stages |
| Feb 2025 03:00 | 238 | 0.3 M people, 631 of 8,719 MW |
| Nov 2026 13:00 | 219 | 15.4 M people, 7,347 of 10,836 MW |
| Nov 2026 20:00 | 222 | 3.9 M people, 1,825 of 10,934 MW |

The corridor result depends on how loaded it was: that matches the CEN account of the 25F. Do not present these numbers as a forecast.

## Assumptions (also returned in every timeline)

See `ASSUMPTIONS` in `engine.py`. The ones that matter most: the 120% opening threshold, 1 s between stages (illustrative), reserve 4% of online synchronous MW, load damping 1.5 %/Hz, no generation ride-through trips, flow DC without voltage. A click on a map line cuts the whole reduced line: where several circuits run in parallel (for example the four 500 kV circuits Alto Jahuel-Ancoa) that is the whole corridor, not one circuit.

## Not done

N-1 base case, the 25F scripted events (220 kV opening at 1.5 s, the north's voltage collapse), batteries as fast injection, ride-through trips, calibration against the CEN 25F numbers (V1 to V9 in `plan.md`).
