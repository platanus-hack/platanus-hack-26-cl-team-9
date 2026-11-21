# Dependency, criticality and heat maps

Last updated: 2026-11-21. Three questions about people and the grid, each with data computed by the backend and a heat map in mapa 3 (layers button, "Mapa de calor"):

| Heat map | Question | Data |
|---|---|---|
| Población | Where do the people the grid serves live? | `data/processed/geo/population.json` (from `node_index.json`) |
| Dependencia de generadores | How many people depend on each generator? | `people_fed` in `web/public/cache/<point>/dependency.json` |
| Criticidad de subestaciones | What dies without backup if a substation falls? | `criticality` in the same file |

Tags: EVIDENCE = measured in this repo. ASSUMPTION = a modelling choice, not verified.

## 1. Population (`build_population_heat.py`)

One point per substation that serves people: `[lon, lat, people]`, 495 points, 18,480,382 people (INE census). `python data/scripts/build_population_heat.py` rewrites it from `node_index.json`.

ASSUMPTION (from `grid_snapshot.json`): each urban census zone goes to its nearest delivery substation; the rural remainder goes to the delivery substations inside the comuna. It is a geographic approximation, not the real feeder map.

## 2. Dependency: who feeds whom (`domain/cascade/tracing.py`)

The data says where plants and people are, but not which plant feeds which people. The DC flow of the base case says how much power crosses every line. With **proportional sharing** (Bialek's downstream tracing) the power that enters a substation is a mix of what reached it, in proportion to the flows: `c[j, g]` is the share of the power at substation j that was generated at g. People fed by g = sum over j of `people_j * c[j, g]`.

ASSUMPTION: proportional sharing is a convention, not a measurement of the real system. The DC flow has no losses, so the MW a generator feeds always equal its own generation; only people are reported.

EVIDENCE (`feb2025-1500`): 114 generating substations; 99% of the people are fed (17.998 M of 18.157 M; the rest live at substations that no power crosses). The biggest dependencies: Cumbre (solar, Atacama) 1.29 M people, Don Héctor 0.93 M, Central Ralco 0.88 M.

## 3. Criticality: what dies without backup (`domain/cascade/criticality.py`)

The number of lines at a substation is a weak proxy for its importance. EVIDENCE: the rank correlation between degree and the load lost elsewhere is 0.39 (`feb2025-1500`) and 0.40 (`nov2026-2000`). A hub inside a mesh can fall with little effect, and a substation with two lines on the north-south backbone can take a third of the country with it (Mauro: 2 lines, 7,568 MW lost elsewhere at 15:00).

So the measure is **simulated**: the substation is switched off (every line that ends at it opens at t = 0) and the cascade engine answers. Measures per substation:

| Field | Meaning |
|---|---|
| `isolated_mw` | Demand of the buses cut off from the main grid. Topology only: no other path exists |
| `collateral_mw`, `collateral_people`, `collateral_share` | Demand the cascade leaves unserved at OTHER buses, as MW, people and share of the national demand. It includes the isolated demand, and what is lost because the backup paths exist but cannot carry the flow (lines trip) or an island falls under 47.5 Hz. The substation's own demand is not counted: it dies by definition |
| `extra_loading` | Largest increase of loading on a surviving line, as a fraction of its capacity (1.0 = the line receives 100 % of its capacity in new traffic). DC flow before the cascade: the stress that triggers it |
| `lines_stressed` | Surviving lines that end above 100 % and gained at least 10 points of capacity |
| `articulation` | Without it the rest of the grid falls apart: no backup path at all |
| `degree` | Number of lines (for comparison; not part of the score) |

**The rule** (`criticality` from 0 to 1):

```
criticality = min(1, max(collateral_share / 0.25, 0.5 * min(1, extra_loading)))
band: alta >= 0.66, media >= 0.33, baja >= 0.05, ninguna below
```

- Real losses decide: losing 25 % of the national demand outside the substation scores 1.
- A substation whose fall only stresses lines tops out at 0.5. That covers the hub that is important but absorbed.

ASSUMPTION (no source, not calibrated): the 25 % saturation, the 0.5 stress weight, the 10-point threshold and the band limits. They are constants at the top of `criticality.py`.

EVIDENCE of the result changing with the hour: at `feb2025-1500` Charrúa (16 lines) and Alto Jahuel (12) score `media` (0.55 and 0.48); at `nov2026-2000` both are `alta` (0.86 and 0.73) and Los Changos and Parinas score 1.0. The same substation has a different importance at a different hour, because the flows are different.

Limits: the measure is for one substation at a time (N-1 on substations); it does not combine failures. The stress uses DC flow, with no voltage. `people` has the known defect (substations with load and 0 people), so `collateral_people` is a lower bound.

## 4. Files and commands

```bash
python data/scripts/build_population_heat.py                              # population.json
cd backend && uv run cascadasen-cache --only dependency                  # dependency.json per point, nothing else is rewritten
```

`dependency.json` (per point, about 55 KB) is keyed by bus id (`B043`) and has every field of section 3 plus `gen_mw`, `people_fed` and `share_of_people`. The web reads it as `DependencyNode` (`web/src/cascade/types.ts`) and draws the heat maps with deck.gl `HeatmapLayer` (`web/src/cascade/heat.ts`). A cache without the file still works: the two heat maps that need it stay empty and say so.

Tests: `backend/tests/unit/test_tracing.py`, `test_criticality.py`, `web/src/cascade/heat.test.ts`.

## 5. Not done

- The heat map of people left without power in a cut, by comuna: the timeline does not say how much load each bus lost, only which buses went dark, and partial shedding would be missing.
- Combining two or more substations out at once.
- Calibrating the criticality constants, or moving them to the YAML parameters with provenance.
