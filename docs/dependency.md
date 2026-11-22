# Dependency, criticality and heat maps

Last updated: 2026-11-22. Three questions about people and the grid as it stands (base case, or after the changes in Estado de la red and their cascade), each with a heat map in mapa 3 (layers button, "Mapa de calor"):

| Heat map | Question | Data |
|---|---|---|
| Población | Where do the people the grid serves live? | `people` per bus of the loaded operating point (no extra file) |
| Dependencia de generadores | How many people depend on each generator? | `people_fed` from `POST /api/v1/grids/dependency` |
| Criticidad de subestaciones | What dies without backup if a substation falls? | `criticality` from the same endpoint |
| Personas sin suministro | Who loses supply at this second? | `people` of the buses in `darkAt(t)`; toggled from the Simulación tab, not the Capas menu |

Tags: EVIDENCE = measured in this repo. ASSUMPTION = a modelling choice, not verified.

## 1. Population

One point per substation with people: `people` of the operating point (`buses.json` in the cache, or `operating` of a composed grid), at the substation's position. No extra file or server call.

ASSUMPTION (from `grid_snapshot.json`): each urban census zone goes to its nearest delivery substation; the rural remainder goes to the delivery substations inside the comuna. It is a geographic approximation, not the real feeder map. `people` has the known defect of substations with load and 0 people (`docs/minimum-dataset.md`).

## 1.1 Affected population (Simulación tab)
The heat map "Personas sin suministro" (heat kind `affected`, `web/src/cascade/heat.ts`) weighs each substation without supply at the current second (`frame.dark`) by its `people`, so it grows as the cascade plays. The card "Comunas sin suministro" groups the same people by comuna with `affectedByComuna` (`web/src/cascade/affected.ts`), using `web/public/cache/comunas-<year>.json` (the per-comuna split behind `people`, from `comunas[].served_by`). Each bus's split is scaled to its current `people`.
ASSUMPTION: a comuna that is only partly without supply (some of its substations still have supply) reads "estimado", because its count depends on the comuna-to-substation split above. A comuna whose substations are all dark counts every person the model assigns to it. A dark substation with no split (old cache, or a substation added in a session) is listed under its own name, also "estimado". People cut by EDAC in islands that survive are not per bus, so the card reports them on one separate line.
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

## 4. API and code

`POST /api/v1/grids/dependency` with `{point, open_lines, out_buses, changes, criticality}` (the changes of Estado de la red; empty for the base case). `criticality` defaults to `true`; with `false` the answer has only who feeds whom. `application/grid_dependency.py` (`GridDependency`) applies the substations out of service (overlay `in_service: false`, shared with `/grids/simulate` through `prepare_edits`), runs the cascade of the cut lines, and measures tracing and criticality on what is left: the settled generation and load and every line that ended open. Criticality runs one cascade per substation still in service, which is almost all of the time. Measured on an Apple M4 after the 2026-11-22 speedup (LU solve in the DC flow, invariants computed once, tighter frequency loop): 0.17 s for the 25F, 0.58 to 0.76 s for a base hour, 1.88 s for Charrúa out; production (Fargate) runs about 6x slower. Tracing alone takes 2 to 5 ms, so Dependencia asks with `criticality: false` and never waits for Criticidad. The last 32 results (keyed by the changes and the flag) are kept in memory per process. At API startup a background thread fills that memory with the full answer for the base case of every hour and the three Desastres (`GridDependency.warm_workflow`, `DISASTERS` in `grid_dependency.py`, kept in sync with `web/src/cascade/Scenarios.tsx`); the health check and the other routes keep answering meanwhile. `CASCADASEN_WARM_DEPENDENCY=false` turns it off. Rate-limited like the cuts.

Response: `{point, open_lines (cuts plus lines the cascade opened), out_buses, nodes}`. `nodes` is keyed by bus id (`B043`) with every field of section 3 plus `gen_mw`, `people_fed` and `share_of_people`; with `criticality: false` each node has only those last three, with the same values and for the same substations. A substation out of service, or with every line open, has no entry. The web reads it as `DependencyNode` (`web/src/cascade/types.ts`), asks only when Dependencia or Criticidad is chosen, one request per kind (`heatRequestKey` in `heat.ts`: Dependencia sends `criticality: false`, Criticidad `true`), and draws deck.gl `HeatmapLayer` (`web/src/cascade/heat.ts`).

Tests: `backend/tests/unit/test_tracing.py`, `test_criticality.py`, `test_grid_dependency.py`, `web/src/cascade/heat.test.ts`.

## 5. Not done

- Calibrating the criticality constants, or moving them to the YAML parameters with provenance.
