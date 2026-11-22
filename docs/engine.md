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
4. **Cascade** (`engine.py`): open the cut, split into islands, settle each island (frequency model), DC flow, open the most overloaded line above 120% of capacity, repeat up to 20 stages. **Stages are causal** (issue #90): the flow of stage k+1 uses the generation and load left after the islands of stage k shed load or went dark, so its opening waits for them. Stage k+1 opens at `max(t_k, last load_shed or island_blackout of stage k) + stage_spacing_s` (1.0 s, illustrative). `island_stable` (the 20 s horizon) does not hold the next stage back. Island events (`island_formed`, `load_shed`, `island_blackout`, `island_stable`) carry `params.stage`, the stage that formed the island. `island_blackout.ids` lists the dark buses (`B###`). A cut that splits nothing emits no `island_formed` (the connected system is not a new island), so a cut with no effect has only its `line_cut` event; a bus with net negative load that ends alone is reported with `load_mw: 0` (`no_load`). Before this change stage k+1 opened at a fixed `(k+1) x 1.0 s`, and in 9 cached cuts a stage-k island went dark after a later opening that had been computed as if it had already settled (for example `nov2026-1300/R026`: the 45-bus island formed at 2.0 s blacks out at 6.59 s, but stages 3 and 4 opened at 3.0 and 4.0 s; they now open at 7.59 and 8.59 s).
5. **Island frequency** (`frequency.py`): `df/dt = f0 * dP / (2E)`, 10 ms step, 20 s horizon, with:
   - E = kinetic energy of the synchronous units online in the island. Solar and wind add none, so a midday point has less inertia (Nov 2026: 26.1 GVAs at 13:00 vs 36.4 GVAs at 20:00). A unit tripped before the transient is already out of E.
   - primary reserve with a 5% droop, capped at 4% of online synchronous MW, time constant 3 s; deployed reserve stays on synchronous units;
   - batteries in fast-frequency mode (theatre `battery_support`): start when f < 49.8 Hz, 200 ms delay, 300 ms ramp (`stack.md` 4.5);
   - load damping 1.5 %/Hz and over-frequency curtailment of solar and wind;
   - EDAC with the real steps (centro-sur table and norte grande Table 3-9 of the CEN 25F report). The extreme-contingency EDAC (671.55 MW by df/dt, [4] Tables 3-10/3-11) is not modelled: on its own it kept the centro-sur island above 47.5 Hz in the 25F, which the real system did not do, because the model has no voltage collapse or generator trips (removed 2026-11-22).
   - **re-split islands** (issue #90). Islands only split as lines open, so every new island is part of one earlier island. A sub-island keeps what its parent used. The engine keeps, per bus, the EDAC steps that fired (`(zone, step)`) and the primary reserve deployed. In the sub-island, steps that already fired shed nothing again (their loads are already off), and the reserve cap is `4 % x (sync MW before the deployed reserve) + extra - reserve already deployed` (the governor gain is unchanged). The sub-island starts its transient at 50 Hz, with the inertia of the units still online (assumption: it does not start at the frequency its parent settled at). `CascadeParams(resplit_memory=False)` brings back the old double counting, only for comparison. Turned on by default on 2026-11-22 (user decision: as realistic as possible).
   Blackout below 47.5 Hz. Each island reports `min_hz`, `final_hz`, `rocof_hz_s` (initial df/dt), `inertia_mws`, `shed_mw` and `battery_mw`.
6. **Voltage collapse, a rule** (`engine.py`, `stack.md` 4.6): the DC model has no voltage. When the 25F corridor separates (its two ends, Nueva Maitencillo and Nueva Pan de Azúcar, end up in different islands) with a pre-fault flow above 1,600 MW N→S or 1,000 MW S→N, both islands collapse by voltage: `island_blackout` with `reason: "voltage"`, and the island in `summary.islands` carries `reason: "voltage"`. It is the only corridor with published limits. The health index marks that report uncertain (a rule, not a calculation). There is no `voltage_limited` result or `summary.uncertain` any more.
7. **Failure cost** (`engine.py::failure_cost`, issue #72): every timeline `summary` carries `unserved_energy_mwh`, `failure_cost_usd` and `outage_duration_h: {value, is_assumption}`, computed by `outage_cost` in `domain/simulation/consequence.py` (the theatre's formula) as `load_shed_mw` x 4 h (`physics.yaml` `default_outage_h`, assumption) x 1,000 x 8.79 US$/kWh (CNE [19]). A regulatory valuation, not a measured loss. When the voltage-collapse rule darkens the 25F islands (`reason: "voltage"`), the cost counts that rule-based load (`health.cost.voltage_rule: true`). The cache and the session sandbox also attach `health`, the after-cut index with its cost (`health.md`).

**25F check (V1 on this network, not hand-tuned):** at Feb 2025 15:00 the pre-fault DC flow is 1,905 MW on the 500 kV line and 287 MW on 220 kV (targets 1,800 and 314 MW, ±15%). Reactances are PyPSA-CL values, not calibrated; they are not real line data either.

## Run

```bash
cd backend
uv run cascadasen-cache            # writes web/public/cache/ (about 46 MB, 4 hours x (273 line cuts + 188 substation shutdowns `sub-B###` + `health.json`))
uv run pytest tests/unit/test_cascade.py
```

The data scripts need the PyPSA-CL files in `data/raw/pypsa_cl/` (they download them): `build_operating_points.py`, then `build_baseline_opf.py` (needs `scipy`).

## Results so far (reduced network, base cases of `baseline_opf.json`)

| Hour | Cuts with no effect (of 273) | 25F corridor cut |
|---|---|---|
| Feb 2025 15:00 | 217 | 18.2 M people, 11,096 of 11,096 MW, 2 stages, both islands collapse by voltage at 2.0 s |
| Feb 2025 03:00 | 231 | 0.3 M people, 631 of 8,719 MW (corridor S→N under 1,000 MW: no voltage collapse) |
| Nov 2026 13:00 | 204 | 18.2 M people, 10,836 of 10,836 MW, 2 stages, voltage collapse |
| Nov 2026 20:00 | 213 | 15.4 M people, 6,738 of 10,934 MW (1,287 MW N→S, under the limit), 3 stages (the third waits until 6.48 s); the re-split 98-bus island collapses by frequency at 25.6 s |

Re-measured 2026-11-22 after issue #90. Before it the rows read 16.8 M, 0.3 M, 17.0 M and 3.9 M people (MW: 11,096, 631, 10,836 and 1,825). Three changes:

- **Causal stages** move only times, never people or MW: the flow of each stage already used the settled state.
- **People in dark buses count whole**, whatever their net load (user decision). Before, a bus with net load zero or below counted nobody even when dark: at Feb 2025 15:00, 25 buses with net negative load hold 1.08 M people and buses at 0 MW hold 0.31 M. A whole-system blackout now gives the 18.16 M people the model assigns (the real 25F: about 19 M, 98.5 %, figure given by the team, source to cite). The gap left is the population the INE comunas do not assign to any node (`minimum-dataset.md`). Engine `_timeline`, theatre `grid.py` and criticality share `people_out_by_bus`; the web `impactAt` follows the same rule. Live buses still count the shed share of their positive load.
- **Re-split islands keep what they used** (item 5). Only Nov 2026 20:00 moves, see below. Of the 1,848 cached timelines, 52 change their MW and 8 their number of stages.

**Nov 2026 20:00, why 3.9 M became 15.4 M (real physics, not a horizon artefact).**

1. Stage 2 splits the system into 115 + 73 buses. The 115-bus island (5,704 MW of generation for 7,337 MW of load) sheds EDAC steps 1-5 (1,517 MW), deploys its whole primary reserve and holds at 49.4 Hz.
2. Stage 3 (6.48 s) opens R065 and cuts off 17 buses that held a 342 MW surplus. The remaining 98-bus part has 4,871 MW for 5,221 MW: a 350 MW deficit.
3. That part has no reserve left (cap 0 MW: all 4 % was deployed) and only EDAC step 6 left (103 MW at 48.3 Hz). Load damping (1.5 %/Hz x 5,221 MW = 78 MW/Hz) would need a 3.2 Hz drop to cover the remaining 247 MW, which means about 46.8 Hz, below 47.5 Hz. So it must collapse.
4. With 30 GVAs of inertia and a small deficit it falls slowly, and the collapse comes 19.1 s after the split (25.6 s). Runs with a 30, 60 and 120 s horizon give the same collapse at 25.6 s, so the 20 s horizon does not decide it.
5. Before #90 the sub-island fired steps 1-5 again (1,182 MW of load that was already off) and counted 110 MW of reserve that was already deployed, so it held at 49.0 Hz.

Not modelled, and it would act in this window in the real system: secondary control (AGC) and operator load shedding. Read this row as "without operator action within about 20 s". Pinned by `tests/validation/test_results_so_far.py`. The corridor result depends on how loaded it was: that matches the CEN account of the 25F. Do not present these numbers as a forecast. A health index built on these results is in [`health.md`](health.md).

## Hand-checked cuts (issue #90)

Followed stage by stage from the cache (`web/public/cache/<point>/<cut>.json`): the islands with gen/load after settling, and the most loaded lines with their DC flow and loading. Checked 2026-11-22.

| Cut | Stage, t | Islands (buses: gen/load MW) | Most loaded lines (flow MW / capacity MW, loading) | What happens |
|---|---|---|---|---|
| 25F, `feb2025-1500/R239` | 0, 0.0 s | 188: 11,096/11,096 | R254 2,042/500 (408 %), R157 989/250 (396 %), R217 1,057/500 (211 %) | Worst only: R254 opens at 1.0 s. R157 is re-evaluated: 131 MW (52 %) once R254 is open |
| | 1, 1.0 s | 188: 11,096/11,096 | R216 2,205/78 (2,827 %), R203 408/225 (181 %), R240 1,642/930 (176 %) | R216 opens at 2.0 s and splits the corridor |
| | 2, 2.0 s | 115 and 73, both dark | none | The corridor ends separate with 2,209 MW N→S before the fault (limit 1,600): both islands collapse by voltage at 2.0 s |
| `nov2026-1300/R026` (4 stages, re-split; 5.7 M people) | 0, 0.0 s | 188: 10,836/10,836 | R109 129/106.7 (120.4 %), R061 543/500 (109 %) | R109 opens at 1.0 s |
| | 1, 1.0 s | 188 | R061 672/500 (134 %), R130 35/30 (116 %) | R061 opens at 2.0 s; R130 stays under 120 % |
| | 2, 2.0 s | 143: 9,395/8,723 surplus (curtails to 8,766/8,723); 45: 1,441/2,112 | R063 111/75 (148 %) | The 45-bus island sheds steps 1-6 (2.32-3.99 s) and still blacks out by frequency at 6.59 s. R063 waits and opens at 7.59 s (was 3.0 s) |
| | 3, 7.59 s | 143 | R062 613/500 (123 %), R185 581/500 (116 %) | R062 opens at 8.59 s (was 4.0 s) |
| | 4, 8.59 s | 142: 8,155/8,725; 1 (611 MW of generation, no load) | all under 93 % | The lone bus goes dark (`no_load`). The 142-bus island sheds steps 1 and 3 (it had shed nothing before) and settles at 8,080/8,054 |
| `feb2025-1500/R090` (1-bus island) | 0, 0.0 s | 188 | R204 340/210 (162 %), R205 300/270 (111 %) | R204 opens at 1.0 s |
| | 1, 1.0 s | 187: 10,658/10,998; 1: 437/97 | all at or under 101 % | The lone bus has a 340 MW surplus: over 52 Hz, dark at 1.39 s. The 187-bus island falls slowly and sheds step 1 (501.6 MW) at 12.26 s; 0.9 M people |
| `nov2026-2000/R239` (re-split collapse; 15.4 M people) | 0, 0.0 s | 188: 10,934/10,934 | R254 1,527/500 (305 %), R157 682/250 (273 %) | R254 opens at 1.0 s |
| | 1, 1.0 s | 188 | R216 1,633/78 (2,094 %), R156 569/400 (142 %) | R216 opens at 2.0 s; the pre-fault flow was 1,287 MW N→S, under the 1,600 MW limit: no voltage rule |
| | 2, 2.0 s | 115: 5,704/7,337 (settles at 5,812/5,820); 73: 5,230/3,597 (curtails to 3,641/3,597) | R065 342/182.9 (187 %), R122 340/182.9 (186 %) | The 115-bus island sheds steps 1-5 (2.38-5.48 s). R065 waits and opens at 6.48 s |
| | 3, 6.48 s | 98: 4,871/5,221 with no reserve and only step 6 left; 17: 941/599 | all under 103 % | The 98-bus island sheds step 6 at 13.8 s and collapses by frequency at 25.6 s (see "Results so far") |
| No effect, `feb2025-1500/R000` | 0, 0.0 s | 188 | the lines at their base-case limit (100 %) | Nothing above 120 %: one event (`line_cut`), 20 s timeline |

Findings of the review:

- **Causality** was broken before #90. With island events tagged by stage, 98 of the 1,844 cached cuts (273 lines + 188 substations x 4 hours) had a `load_shed` or `island_blackout` of a stage-k island after a stage k+1 opening; 10 if only blackouts count. After the fix: 0.
- **One line per stage** is the `stack.md` 4.3 rule. The other lines above 120 % are re-evaluated with the new flows (25F stage 0: R157 at 396 % does not open once R254 is open). Test: `test_only_the_worst_overload_opens_and_the_rest_is_re_evaluated`.
- **Flow of stage k+1** uses `s.gen` and `s.load` after the EDAC, blackouts and reserve of stage k, not the operating point.
- **Islands without generation or load** go dark (`no_generation`, `no_load`) and enter `dark`. All their people count in `people_without_power`, whatever their net load (fixed in #90).
- **The 25F voltage rule** uses the pre-fault flow (`prefault_boundary_mw`, computed before the cascade) and darkens both islands.
- **Settled islands are balanced** within 5 % of their load (largest residual in the cache: 4.4 %), because damping and curtailment absorb the rest. An island whose EDAC step fires late (after about 12 s) can end the 20 s horizon unsettled: the toy grids in the tests do. No real cached cut showed it beyond 4.4 %.
- **`truncated`** is set when the 20-stage cap is reached. No cached cut reaches it.
- **Re-split islands double counted EDAC and reserve** before #90: a sub-island ran the full EDAC table again and counted its parent's deployed reserve. Fixed and on by default (item 5).

## Cost

The summary of every timeline carries `failure_cost_usd`, `cost_per_hour_usd`, `unserved_energy_mwh`, `outage_duration_h`, `dark_load_mw` and `cost_breakdown`. `POST /api/v1/grids/cost` (`{point, open_lines, out_buses}`) returns the same for the changes of Estado de la red. The formula tells a total blackout from a slow grid (`blackout_cost` in `domain/simulation/consequence.py`, parameters in `cascade.yaml` `cost`):

```
cost      = VoLL x [ dark_MW x H_blackout x (1 + (k - 1) x dark_share) + shed_MW x H_shed ]
cost/hour = VoLL x [ dark_MW x (1 + (k - 1) x dark_share) + shed_MW ]
```

| Term | Value | Source |
|---|---|---|
| `dark_MW` | demand of the buses that went dark (islands that collapsed, substations out of service) | engine |
| `shed_MW` | load cut by EDAC in islands that survive (a slow grid, no black start) | engine |
| VoLL | 8.79 US$/kWh | CNE failure cost [19] |
| `H_blackout` | 7.34 h of black start | [44]: 81,430 MWh not served in the 25F over 11,096 MW. Cross-check: the restoration reports give 8.2 h (Gobierno) or 5.4 h (CEN) |
| `H_shed` | 1 h | ASSUMPTION: EDAC load is back once the frequency recovers |
| `k` | 1.375 | [44]: US$ 984 M / 81,430 MWh = 12.08 US$/kWh over 8.79: a total blackout also stops transport, water, telecom and industry. ASSUMPTION: it grows linearly with `dark_share` |

EVIDENCE (`POST /grids/cost`, 2026-11-22): 25F US$ 984.3 M and 81,443 MWh (the study: US$ 984 M, 81,430 MWh), US$ 134 M per hour; the same cut at 03:00 sheds 631 MW and costs US$ 5.5 M (1 h, no premium); Apagón 2011 analogue US$ 67 M; Terremoto 2010 analogue US$ 102 M. The 25F matches by construction of `H_blackout` and `k`, which come from the same study; the other cases are not calibrated. Callers that only know the MW lost (the N-1 money at risk of `health.py`) count them as dark without the premium.

## Assumptions (also returned in every timeline)

See `ASSUMPTIONS` in `engine.py` and the `is_assumption` entries of `cascade.yaml`. The ones that matter most: the 120% opening threshold, 1 s between stages (illustrative; a stage also waits until the islands of the previous one finish their EDAC steps or go dark), reserve 4% of online synchronous MW with 5% droop, load damping 1.5 %/Hz, no generation ride-through trips, flow DC without voltage. A click on a map line cuts the whole reduced line: where several circuits run in parallel (for example the four 500 kV circuits Alto Jahuel-Ancoa) that is the whole corridor, not one circuit.

## Not done

N-1 base case, the 25F scripted events (220 kV opening at 1.5 s; the north's voltage collapse stays documented, not computed), ride-through trips, battery energy limits, calibration of the island frequency against the CEN 25F numbers (V2 to V9 in `plan.md`; only the V1 flow split is checked on this network). The 13-area engine keeps those cases.
