# Grid health index (margin to the limit)

Status: implemented in `backend/src/cascadasen/domain/cascade/health.py` (with the failure cost next to it, section "Cost"), parameters in `domain/cascade/params/health.yaml`, command `cascadasen-health`, tests in `tests/unit/test_health.py` and `tests/validation/test_health_25f.py`.

It is **our own model index**, not an indicator published by the Coordinador (CEN) or the SEC. In the UI call it "índice de margen operativo (modelo)", never "salud de la red" without that qualifier.

## Rule

Each metric becomes a margin: 1 with room to spare, 0 at its limit, negative beyond it. `raw` keeps the unclipped value (for example -0.38 when the corridor carries 38% more than its limit), `value` is clipped to 0-1. The index is the **minimum** of the margins flagged `in_index`: the weakest link decides and a good margin elsewhere does not compensate. The report also gives `binding` (the metric that limits), `mean` (information only), `uncertain` and, per margin, its limit and source or `is_assumption`.

Two indices, on different scales. Do not compare a pre-fault value with an after-cut value.

## Pre-fault index (`prefault_health`)

| Key | Margin | Limit and source | In the index |
|---|---|---|---|
| `transfer_25f` | `1 - |flow| / limit` through the 25F corridor (`boundary_flow_mw`) | 1,600 MW north to south, 1,000 MW south to north: validity range of the defence scheme [4] (`cascade.yaml` `voltage_limit`) | Yes |
| `inertia` | `(E - 31,000) / (42,400 - 31,000)` MWs | 31.0 to 42.4 GVAs per CEN scenario (`datasets.md`, not re-checked): ASSUMPTION | Yes |
| `frequency_n1` | `(nadir - 47.5) / (49.0 - 47.5)` after losing the largest synchronous bus, whole system as one island | 47.5 Hz blackout (NTSyCS art. 3-10), 49.0 Hz first EDAC step [4]. The largest synchronous bus stands for the largest unit: ASSUMPTION. Also reports RoCoF | Yes |
| `n1_security` | Share of the single-line cuts with no effect (shed under 1 MW) | N-1 asks for all of them | Yes |
| `n1_worst` | `1 - worst cut MW / demand` | Information only | No |

`n1_worst` stays out because cutting a reduced line cuts the whole corridor (for example the four 500 kV circuits Alto Jahuel-Ancoa): at `feb2025-0300` that blacks out the whole system, an artefact of the reduction and not a real N-1. The maximum line loading of the base case is also left out: the base-case OPF puts the most loaded line at 100% by construction.

## After-cut index (`event_health`)

Runs `run_cascade_workflow` and reads its `summary`.

| Key | Margin |
|---|---|
| `supply` | `1 - load shed / total load` |
| `frequency_islands` | Worst `(min_hz - 47.5) / 1.5` among islands that maintain. A `blackout` island scores 0. An island that collapsed by voltage (`reason: "voltage"`) scores 0 and marks the report `uncertain`: the 25F voltage collapse is a rule, not computed (`engine.md`) |

## Result (2026-11-21, `cascadasen-health`)

Reference for "healthy": `feb2025-0300`, the same 2025 network and month as the 25F, so the comparison isolates the operating point.

| | 25F (`feb2025-1500`) | Reference (`feb2025-0300`) |
|---|---|---|
| Pre-fault index | **0.00**, limited by `transfer_25f` (2,209 MW N→S, limit 1,600; raw -0.38) | **0.35**, limited by `transfer_25f` (653 MW S→N, limit 1,000) |
| Other pre-fault margins | inertia 0.50 (36.7 GVAs), `frequency_n1` 1.00, `n1_security` 0.80 (218/273) | inertia 1.00 (49.3 GVAs), `frequency_n1` 0.93, `n1_security` 0.85 (231/273) |
| After cutting R239 | **0.00**, uncertain (collapse by voltage, a rule; 11,096 of 11,096 MW lost) | **0.67**, limited by `frequency_islands` (48.5 Hz; 631 of 8,719 MW lost) |

Reading: the index separates the two cases mainly through the corridor transfer, which is the documented cause of the 25F. Inertia and the frequency after losing the largest unit do not limit either case. The reference is not "fully healthy" (0.35) because its corridor already carries 65% of its south-to-north limit.

## Cost (issue #72)

The index and the failure cost sit side by side, never merged: there is no "index in dollars" and money does not weight the margins (the weights would have no source, same rule as #59).

| Figure | Where | How | Quality |
|---|---|---|---|
| `cost.cost_usd` (after a cut) | `event_report` / `event_health`, `extra["cost"]` | `failure_cost_usd` of the cascade summary: `load_shed_mw` x `outage_duration_h` x 1,000 x 8.79 US$/kWh, by `outage_cost` (`consequence.py`) | Modelled, regulatory valuation (CNE [19]) |
| `cost.voltage_rule` | same | `true` when islands went dark by the 25F voltage-collapse rule (`reason: "voltage"`): that load is lost by a documented rule, not a computed collapse | Modelled |
| `cost.n1_expected_cost_usd` (before a cut) | `prefault_health`, `extra["cost"]` | Mean cost of the 273 single-line cuts, each line with the same weight | Modelled. ASSUMPTION: equal probability per line (no published failure rates) |
| `cost.n1_worst_cost_usd` | same | Cost of the worst single cut | Modelled; the same artefact as `n1_worst` (a reduced line cuts a whole corridor) |
| `cost.n1_cost_share` | same | Count (5) and a 20-point band of the share of the expected cost carried by the 5 costliest cuts | Modelled |
| `outage_duration_h` | both | `physics.yaml` `default_outage_h` = 4 h, `is_assumption: true`; fixed in map 3 | Assumption |

Rules:
- The cost and `supply` come from the same MW lost: `cost = (1 - supply) x total load x h x 1,000 x 8.79`. The index is a minimum, so when `frequency_islands` binds the index drops without the cost moving. Show both; do not fuse them.
- No line ids for the costliest cuts anywhere (`cyber.md` section 8): totals, counts and bands only. For the same reason the `n1_worst` margin no longer names its line.
- The N-1 cost reuses the single-cut runs: `prefault_health(..., n1_results=...)` takes them from the cache builder, so no cut runs twice.
- The cost is a valuation for planning, not "what the country lost". The UI says "valoración regulatoria (costo de falla CNE), 4 h supuestas".

Result (2026-11-21, `cascadasen-health`, 4 h):

| | 25F (`feb2025-1500`) | Reference (`feb2025-0300`) |
|---|---|---|
| After cutting R239 | US$ 390.1 M (11,096 MW, 44,384 MWh, the whole system; `voltage_rule`) | US$ 22.2 M (631 MW) |
| N-1 expected / worst | US$ 7.5 M / US$ 390.1 M; 55 of 273 cuts with cost, the 5 costliest carry 60-80 % | US$ 4.5 M / US$ 306.6 M; 42 of 273, the 5 costliest carry 80-100 % |

Validation against the 25F (ASSUMPTION, only to order magnitudes; `tests/validation/test_health_25f.py`): a full blackout of 11,096 MW for 4 h is about US$ 390 M. The press estimate of the 25F loss is US$ 984 M (`datasets.md` [44], not verified); a full blackout would need about 10.1 h of average unserved energy to reach it. Since the voltage-collapse rule (#76) the model loses the whole system after cutting R239, so the gap is the assumed 4 h duration (and the press figure measuring more than unserved energy). The test pins the figures and does not tune the duration. The US$ 984 M figure is not shown in the UI.

Where it shows: `cascadasen-health` (a `$` line under each report, and `cost` in `--json`), the web cache (`<point>/health.json`, `health` in every cut timeline), the session sandbox timeline (`health`), `POST /api/v1/grids/simulate` (`health`, and the summary cost includes the direct loss of substations out of service), and the map 3 Simulación tab (`mapa3.md` section 4, item 5).

## Cautions

- Limits marked ASSUMPTION are placeholders until checked against the source. The index is only as good as the corridor limit, which is the one published figure.
- One corridor has published limits (`engine.md`), so the transfer margin exists for that corridor only. No margin exists for other corridors, voltage, short-circuit strength (SCR) or reserve.
- Operating points are modelled (PyPSA-CL), not measured.
- The index measures effect on the grid, never the cause of an event (`cyber.md` section 8).

## Run

```bash
cd backend
uv run cascadasen-health                        # 25F against feb2025-0300, before and after R239
uv run cascadasen-health --points nov2026-2000 --cut      # other points, pre-fault only
uv run cascadasen-health --json                 # includes the cost object of each report
uv run cascadasen-cache                         # writes <point>/health.json and `health` in every cut timeline
uv run pytest tests/unit/test_health.py tests/validation/test_health_25f.py -s   # -s prints the 25F cost figures
```

## Not done

Per-node index, SCR, reserve margin, an HTTP endpoint, calibration of the weights and thresholds against the CEN account of the 25F. Cost: failure rates per line (the N-1 expected cost uses equal weights), a duration per consequence level, an editable duration in map 3, CLP, an economic model by region or sector. The pre-fault `health.json` describes the base network only, so a session with dataset edits shows no pre-fault row.
