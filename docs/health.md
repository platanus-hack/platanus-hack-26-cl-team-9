# Grid health index (margin to the limit)

Status: implemented in `backend/src/cascadasen/domain/cascade/health.py`, parameters in `domain/cascade/params/health.yaml`, command `cascadasen-health`, tests in `tests/unit/test_health.py` and `tests/validation/test_health_25f.py`.

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
| `frequency_islands` | Worst `(min_hz - 47.5) / 1.5` among islands that maintain. A `blackout` island scores 0. A `voltage_limited` island scores 0 and marks the report `uncertain`: the 25F voltage collapse is documented, not computed (`engine.md`) |

## Result (2026-11-21, `cascadasen-health`)

Reference for "healthy": `feb2025-0300`, the same 2025 network and month as the 25F, so the comparison isolates the operating point.

| | 25F (`feb2025-1500`) | Reference (`feb2025-0300`) |
|---|---|---|
| Pre-fault index | **0.00**, limited by `transfer_25f` (2,209 MW N→S, limit 1,600; raw -0.38) | **0.35**, limited by `transfer_25f` (653 MW S→N, limit 1,000) |
| Other pre-fault margins | inertia 0.50 (36.7 GVAs), `frequency_n1` 1.00, `n1_security` 0.80 (218/273) | inertia 1.00 (49.3 GVAs), `frequency_n1` 0.93, `n1_security` 0.85 (231/273) |
| After cutting R239 | **0.00**, uncertain (collapse by voltage, a rule; 11,096 of 11,096 MW lost) | **0.67**, limited by `frequency_islands` (48.5 Hz; 631 of 8,719 MW lost) |

Reading: the index separates the two cases mainly through the corridor transfer, which is the documented cause of the 25F. Inertia and the frequency after losing the largest unit do not limit either case. The reference is not "fully healthy" (0.35) because its corridor already carries 65% of its south-to-north limit.

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
uv run cascadasen-health --json
uv run pytest tests/unit/test_health.py tests/validation/test_health_25f.py
```

## Not done

Per-node index, SCR, reserve margin, an HTTP endpoint and a `health.json` in the web cache, calibration of the weights and thresholds against the CEN account of the 25F.
