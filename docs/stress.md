# Prepared scenarios: batch changes for the MCP

A prepared scenario changes the grid before any failure: more people in a place, more demand, less generation of a technology, weaker lines. One request can change many elements at once through filters ("every hydro plant", "every 220 kV line in the centre"). These batch changes exist for the model (MCP clients and the in-app assistant). A person in the web edits one component at a time in its card (section 10).

The rule that matters: **preparing never simulates.** `POST /grids/prepare` only resolves the changes and returns the prepared grid. A failure on that grid runs in the existing cascade (`POST /grids/simulate`), which takes the same `changes`. The cascade logic is the one the app always used. The changes only alter the grid it starts from.

Code: `backend/src/cascadasen/application/grid_stress.py` (filters and changes), `api/stress_schemas.py` (bodies), `api/grid_routes.py` (routes), `mcp/tools.py` (`prepare_scenario`). Tests: `backend/tests/unit/test_grid_stress.py`, `test_prepare_scenario_tool.py`.

## 1. Flow

```
changes ──► POST /grids/prepare ──► what each change touches, prepared totals,
                                    lines already over their limit, who each generator should feed
changes + failures ──► POST /grids/simulate ──► cascade timeline + supply (should feed vs feeds)
```

1. Write the `changes` (section 3).
2. Optional: call `/grids/prepare` to check what they touch. It is cheap: no cascade.
3. Add at least one failure (`open_lines` or `out_buses`) and call `/grids/simulate` with the same `changes`.
4. To compare, call `/grids/simulate` with the same failures and no `changes`.

Nothing is stored. Each request carries the whole scenario, like the cuts do. There is no cooldown. The point (hour) is part of each request, and changing it starts from that point's base grid.

## 2. Endpoints

| Route | Agent operation | Does |
|---|---|---|
| `POST /api/v1/grids/prepare` | `prepare_scenario` | Resolves `changes`. No cascade. |
| `POST /api/v1/grids/simulate` | `simulate_grid` | Cascade of `open_lines` + `out_buses` on the grid prepared with `changes`. At least one failure. |
| `POST /api/v1/grids/dependency` | (web only) | Heat maps on the prepared grid after the failures. |
| `POST /api/v1/grids/cost` | (web only) | Failure cost on the prepared grid. |
| `GET /api/v1/grids/places?q=Iquique` | `resolve_place` | The one substation a place resolves to, with `how` (the rule of `places`, section 3.1). The MCP session tools `add_datacenter` and `add_generator` call it. |
| `GET /api/v1/grids/lines?q=Ancoa – Alto Jahuel` | `find_line` | The lines a person names, in id order (section 3.2). The MCP tool `find_line` calls it; its ids go in `open_lines`. |

The agent operations are in `docs/openapi/agents.openapi.json` (tag `grid-stress`), with every field described. Bodies:

```json
POST /grids/prepare   {"point": "feb2025-1500", "changes": [ ... ]}
POST /grids/simulate  {"point": "feb2025-1500", "open_lines": ["R239"], "out_buses": [], "changes": [ ... ]}
```

`point`: `feb2025-1500` (25F reference, 11,096 MW), `feb2025-0300` (minimum demand, 8,719 MW), `nov2026-1300` (solar noon, 10,836 MW), `nov2026-2000` (evening peak, 10,934 MW).

## 3. The change object

```json
{"target": "generation", "tech": ["hidro"], "zones": ["CS"], "factor": 0.5}
```

| Field | Type | For | Meaning |
|---|---|---|---|
| `target` | `population` \| `demand` \| `generation` \| `lines` | all | What changes. |
| `factor` | number, 0 to 5 | all | Multiplies each picked element (lines: capacity). `0` removes it, `1` changes nothing. |
| `add` | number | population, demand, generation | One total for the whole filter: people for `population`, MW otherwise. Negative lowers it. Split by each element's current value, or evenly when they are all zero. |
| `x_factor` | number, over 0 to 5 | lines | Multiplies the reactance `x_pu`. The DC flow uses reactance: a higher value moves flow to other paths. |
| `buses` | `["B062"]` | population, demand, generation | Substation ids. |
| `zones` | `["NG"]` | all | `NG` Norte Grande, `NC` Norte Chico, `CE` Centro, `CS` Centro-sur, `SU` Sur. |
| `areas` | `["A09"]` | all | Operating areas (table below). |
| `comunas` | `["Puente Alto"]` or `["13201"]` | population, demand | Comuna by name or CUT code: every substation that serves it. Not combined with `buses`, `zones`, `areas` or `places`. |
| `places` | `["Iquique"]` | population, demand, generation | Places as a person names them, each resolved to **one** substation (section 3.1) and added to `buses`. Use it to put a point: a datacenter, a plant, a battery. Up to 10. |
| `tech` | `["hidro"]` | generation | `hidro`, `solar`, `eolica`, `carbon`, `gas`, `diesel`, `bioenergia`, `geotermica`, `bateria` (new capacity only). `termica` = `carbon` + `gas` + `diesel`. |
| `lines` | `["R239"]` | lines | Line ids. |
| `kv` | `[220]` | lines | Voltage levels: 66, 110, 154, 220, 500. |

Rules:
- `population`, `demand` and `generation` take **one of** `factor` or `add`. `lines` takes `factor`, `x_factor` or both, and never `add`.
- **Filters combine with AND.** `{"tech": ["hidro"], "zones": ["CS"]}` is hydro in Centro-sur. **No filter means the whole country.**
- For lines, `zones` and `areas` pick lines with **both ends** inside.
- Changes apply **in order**: a `demand` factor after a `population` change multiplies the demand that already grew with the people.
- Up to **20 changes** per request. The overlay limits hold: 5,000 MW changed in total (load + generation) and 3,000 MW per bus. Over a limit the request is 422 (section 8).
- No value goes below zero. A base load that is already negative stays as it was: 28 buses at feb2025-1500 and 27 at nov2026-1300 inject embedded generation.

### 3.1 Places (`application/places.py`)

A place resolves to one bus, in this order, and the report of the change says which one and how (`places: [{place, bus, bus_name, area, area_name, how}]`):

1. A bus id `B###`, or an area id `A##` (its anchor bus, the one with the largest load).
2. A substation named exactly so, without the "S/E" prefix: `Antofagasta` → S/E ANTOFAGASTA. Of two with that name, the one with no owner in parentheses (`Concepción` → S/E CONCEPCION, not S/E CONCEPCION (FFCC)), then the highest kV.
3. A comuna: the bus of the substation that serves most of its people (`comunas[].served_by`, mapped to the 188 buses like the population). `Iquique` → S/E CONDORES (43 % of its people); no substation is called Iquique.
4. A substation whose name carries an owner (`S/E PUENTE ALTO (CMPC)`, a paper mill): only after the comunas, so `Puente Alto` is the comuna.
5. A region, then a province: the substation of its most populous comuna (`Biobío` → Concepción; `Región Metropolitana`, `Araucanía`, `O'Higgins`, `Aysén` have aliases).
6. An area name: its anchor bus.
7. A unique part of a substation name. Several matches, or none, answer 404 with the candidates or a close spelling ("¿Quisiste decir antofagasta?").

Comunas off the SEN answer 404 "no está conectada al Sistema Eléctrico Nacional": Magallanes and Aysén (no serving bus in the 188-bus grid), and the islands, which the snapshot assigns to a mainland substation over 300 km away (Juan Fernández 705 km, Isla de Pascua 3,734 km; the largest gap of a SEN comuna is 150 km). Leading words such as "cerca de", "en", "comuna de", "región de" are dropped.

Why: the earlier rule matched area names first, so the assistant put a datacenter for "Antofagasta" at S/E ESCONDIDA (140 km away) and one for "Arica" or "Iquique" at S/E COLLAHUASI, a mine inland.

Areas: `A01` Arica–Iquique, `A02` Crucero–Kimal, `A03` Antofagasta–Taltal (NG); `A04` Cumbre–Diego de Almagro, `A05` Copiapó, `A06` Vallenar, `A07` La Serena–Coquimbo (NC); `A08` Los Vilos–Valparaíso, `A09` Santiago (CE); `A10` O'Higgins–Maule, `A11` Biobío (CS); `A12` Araucanía, `A13` Los Ríos–Los Lagos (SU).

### 3.2 Lines by name (`application/line_lookup.py`)

A line of the reduced network has no name of its own: it is named by its two end substations, as the web does ("Nueva Maitencillo – Nueva Pan de Azúcar (500 kV)"). `GET /grids/lines?q=…` (agent operation `find_line`, MCP tool `find_line`) reads:

1. A line id `R###`/`U###`.
2. Two substations, in either order, joined by a dash (–, —, or - with spaces), "a", "y", "hasta", "con" or " / ", optionally after "la línea" or "entre": every line between them. Each end is a substation named exactly so (`Maitencillo` → S/E MAITENCILLO, not S/E NUEVA MAITENCILLO), else every substation whose name contains it. "Nueva Maitencillo – Nueva Pan de Azúcar" → `R239`; "Maitencillo – Pan de Azúcar" → `R216` (the 110 kV line); "entre Ancoa y Alto Jahuel" → `R006`.
3. One substation: every line that ends there.

A voltage in the text ("500 kV") keeps only the lines at that voltage when any match. The answer (`query`, `how`, `matched`, `lines: [{id, name, kv, a, b, capacity_mw}]`, `truncated`) lists at most 12 lines **in id order**: a lookup by name, never a ranking (`cyber.md` section 8). 404 for an unknown substation or two substations with no direct line, 422 for an empty query. Every one of the 273 lines is found by the names of its two ends (`tests/unit/test_line_lookup.py`).

Why: on 2026-11-22 the assistant, asked to cut "la línea Nueva Maitencillo – Nueva Pan de Azúcar", searched the network area by area with `describe_network` (Santiago first) and ran out of its 8 steps.

## 4. What each target does

**population.** It changes people and, with them, demand: `ΔMW = Δpeople × s_reg × demand_total(point) / people_total`, with `s_reg = 0.389` (`cascade.yaml`, `stress.regulated_share`).
- Free clients (mining, industry) used 61.1 % of the SEN in 2024 (Coordinador Eléctrico Nacional, via Enel X). They do not grow with population. The regulated part does: homes, commerce, small firms.
- Per point: 238 W per added person at feb2025-1500, 187 at feb2025-0300, 232 at nov2026-1300, 234 at nov2026-2000 (`per_capita_w` in every response).
- Why not scale each bus's load by its people: load per person is 1,826 W in Norte Grande and 522 W in Centro-Sur, and the top tenth of buses is over 35 kW per person (mines). Doubling the people near a mine would double the mine.
- Check: residential use alone is 778 kWh per person per year, about 89 W on average (CNN Chile). The regulated value also holds commerce and small firms.
- By comuna, the extra people go to the substations that serve the comuna, in the census split (`grid_snapshot.json`, `comunas[].served_by`).
- **Assumption:** the same value per person everywhere.

**demand.** MW alone, population unchanged: another hour, a new industry, a heat wave.

**generation.** The dispatch comes summed per bus (`baseline_opf.json`). Each bus's generation is split by technology in proportion to its plants' installed MW times the national dispatch factor of that technology at the point. Thermal plants go by their first fuel: carbón and petcoke to `carbon`, natural gas and propane to `gas`, petróleo and fuel oil to `diesel`. Cogeneration and "S/I" (22 MW) count only under `termica`, with no dispatch. Synchronous technologies (hydro, thermal, bioenergy, geothermal) move their synchronous MW with them, and inertia follows, capped at 10 s. **Assumption.**
- **New plant.** `add` over 0 where none of the picked buses has the technology builds a new plant there, split evenly (`new_plant: true` in the report, assumption `new_plant`). A synchronous one adds its MW as synchronous with H = 4 s (`overlay.DEFAULT_INERTIA_H`); solar, wind and `bateria` add no inertia, and a battery injects its full power (discharging at the point). It needs one technology, or only synchronous ones: no `tech`, or solar with hydro, is a 422. Before (until 2026-11-22), `add` was split by the MW the technology already had, so a plant at a bus without it added nothing and still answered 200 with `matched: 0`.

**lines.** Capacity (`factor`) and reactance (`x_factor`). The cascade opens a line over its limit.

**Redispatch (every target).** The overlay's rule: the island's synchronous base units take the imbalance, weighted by their synchronous MW. Buses whose generation a change sets take no share. There is no upward capacity limit, so the grid tries to survive and what breaks is the lines. `redispatch` in the response says how much moved. **Assumption.**

## 5. Recipes (real outputs)

**Halve every hydro plant at night.**
```json
{"point": "feb2025-0300", "changes": [{"target": "generation", "tech": ["hidro"], "factor": 0.5}]}
```
`/prepare`: `matched: 45` substations, `gen_delta_mw: -2170.5`. The other synchronous units of each island redispatch 2,171 MW, so total generation stays at 8,719 MW.

**Triple the people of Puente Alto, then lose a substation.**
```json
{"point": "feb2025-1500", "out_buses": ["B020"], "changes": [{"target": "population", "comunas": ["Puente Alto"], "factor": 3}]}
```
- `/prepare`: 4 substations, `people_delta: 1136172`, `load_delta_mw: 270.1`. The prepared grid already loads `R014` at 130.34 %: the cascade starts with it.
- `/simulate` with the changes: 3,715,014 people without power and 1,622.7 MW shed. Without the changes, the same failure leaves 199,962 people without power and sheds 468.7 MW.

**More demand in the north, with its thermal plants off.**
```json
{"point": "feb2025-1500", "changes": [
  {"target": "demand", "zones": ["NG"], "add": 200},
  {"target": "generation", "tech": ["termica"], "zones": ["NG"], "factor": 0}
]}
```
The 200 MW are split over the 39 NG buses with demand, by their current demand.

**Weaker 220 kV lines in the centre.**
```json
{"point": "feb2025-1500", "changes": [{"target": "lines", "kv": [220], "zones": ["CE"], "factor": 0.8}]}
```
27 lines, each at 80 % of its capacity (for example `R003`: 500 → 400 MW).

**One substation with twice the people, from the web card.** `{"target": "population", "buses": ["B062"], "factor": 2}`.

## 6. Responses

`POST /grids/prepare`:
- `changes[]`: per change, `matched`, the deltas (`people_delta`, `load_delta_mw`, `gen_delta_mw`) and `elements` with each value as `[before, after]`.
- `totals`: `people_total`, `load_total_mw` and `gen_total_mw` of the prepared grid.
- `overloaded_lines`: lines over the cascade's limit with no failure (`loading_pct`). A simulation starts by opening them.
- `should_feed`: `sources` (per generating substation, by id) and `by_zone`. With no failure every `pct_fed` is 100.
- `per_capita_w`, `redispatch`, `warnings`, `assumptions` (each with `is_assumption`).

`POST /grids/simulate` adds `supply` to its usual body (`timeline`, `direct`, `dropped_lines`, `warnings`):
- `supply.sources[]`: `id`, `name`, `zone`, `tech` (share per technology), `gen_mw` `[before, after]`, `should_feed` (people it feeds on the prepared grid before the failure), `feeds` (people it still feeds once the cascade settled) and `pct_fed` (percent, 2 decimals).
- `supply.by_zone`: the same added up per zone.
- `pct_fed` over 100 means that source took people other sources fed before. People at a substation out of service count as not fed.
- Sources are ordered by id, never by damage (section 9).

## 7. MCP tool `prepare_scenario`

One tool sets the whole final grid. The web map loads it.

```
prepare_scenario(changes=[...], open_lines=[...], out_buses=[...], point="feb2025-1500")
```

- Every argument is optional. `point` defaults to `nov2026-1300`.
- With `changes`, it calls `/grids/prepare`.
- With failures, it also calls `/grids/simulate` twice, with and without `changes`.
- It needs no session.
- Result:
  - `scenario`: point, changes, open_lines and out_buses as sent.
  - `prepared`: per change, `matched` and deltas, the totals, the number of lines over their limit and `should_feed_by_zone`.
  - `simulation`: `with_changes` and `without_changes` (people without power, load shed, dark load), `lines_opened_by_cascade` and `supply_by_zone`.
  - `notice`.
- In the web the assistant's `scenario` **replaces** the grid on the map. The timeline loads paused at 0 and the user presses play.
- Each call is the full final state. To add a change, send the earlier ones again with it.

Examples:

| User says | Call |
|---|---|
| "Baja a la mitad todas las hidroeléctricas" | `changes=[{"target":"generation","tech":["hidro"],"factor":0.5}]` |
| "Puente Alto con el triple de gente y se cae Charrúa" | `changes=[{"target":"population","comunas":["Puente Alto"],"factor":3}]`, `out_buses=["B043"]` |
| "Sin térmicas en el norte y el 25F" | `changes=[{"target":"generation","tech":["termica"],"zones":["NG"],"factor":0}]`, `open_lines=["R239"]`, `point="feb2025-1500"` |
| "Las líneas de 220 kV del centro al 80 %" | `changes=[{"target":"lines","kv":[220],"zones":["CE"],"factor":0.8}]` |
| "Un datacenter de 120 MW en Antofagasta y una solar de 80 MW en Iquique" | `changes=[{"target":"demand","places":["Antofagasta"],"add":120},{"target":"generation","places":["Iquique"],"tech":["solar"],"add":80}]` |

The tool maps technology names people use before sending (`digest.normalize_tech`): "eólica", "fotovoltaica", "baterías"/"BESS", "biomasa"… and "nuclear" to `termica`, with a note that it is an assumption (there is no nuclear plant in Chile). The prepared summary says, for a change that touched one to five substations, which ones (`at`), and a change that touched none carries a `warning` so the model never reports a plant that was not built.

Ids: `find_line` (a line by its substations, section 3.2), `describe_network` or the web give `B###` and `R###`. The 25F line is `R239`. A line out of service goes in `open_lines` only: a `lines` change with `factor` 0 answers 422 with that hint.

## 8. Errors

| Status | When | Example `detail` |
|---|---|---|
| 422 | `factor` and `add` together, or a filter that does not apply to the target | `demand: indica factor o add, no ambos` · `generation: filtra por buses, zones, areas o tech` |
| 422 | Unknown technology | `changes[0]: tecnologías desconocidas: nuclear (válidas: …)` |
| 422 | Over the overlay limits | `Máximo 5000 MW agregados o cambiados (carga + generación).` |
| 422 | A `lines` change with `factor` 0 (a line with no capacity is a line out of service) | `lines: factor 0 no saca una línea de servicio (la capacidad debe ser mayor que 0). Para sacarla de servicio pon su id R### en open_lines y no agregues un cambio de lines para ella.` |
| 422 | `/simulate` with no failure | `Indica al menos una línea o una subestación` |
| 404 | Unknown point, bus, line, comuna, zone or area | `changes[0]: comuna desconocida: Atlantis (usa el código CUT o el nombre)` |
| 404 | Unknown place, or a comuna off the SEN | `changes[0]: No encuentro el lugar 'Marte'. …` · `La comuna de Punta Arenas no está conectada al Sistema Eléctrico Nacional …` |
| 422 | A new plant with no technology, or mixing synchronous and not | `changes[0]: una central nueva necesita su tecnología (tech)` |

`changes[i]` names the change that failed. The MCP client turns `detail` into the tool error.

## 9. Guardrails

- The changes are a scenario to study, not a search. No endpoint or tool tries combinations or looks for the change that hurts most. Sources are listed by id, and the tool gives the model only the per-zone stat (`docs/cyber.md` section 8.2).
- Results carry the notice "Escenario hipotético: se modela el efecto, no el ataque."
- Values the model adds (per-capita demand, technology split, redispatch) come with `is_assumption: true`. Say so.

## 10. Web map

- **Edit in place.** The card of a selected substation has factors for Personas, Demanda and Generación. The card of a line has one for Capacidad. A factor applies on Enter or when the field loses focus, and 1 removes it. Each one writes a change for that component alone (`{"target": "population", "buses": ["B062"], "factor": 2}`), kept with the cuts in `Edits.changes` (`web/src/cascade/edits.ts`, also in localStorage).
- **Batch changes only from the assistant.** "Estado de la red" lists every change, with "Quitar" on each.
- **Simulation.** With changes, the web never reads the precalculated cache: `/grids/simulate`, `/dependency` and `/cost` get `changes`. With changes and no failure, the map shows the base case, and the panel shows the prepared grid: totals, lines already over their limit, and the prepared values in the card. "Simulación" shows `supply` per zone, and a generating substation's card shows its own numbers.
- **Reset.** Opening a disaster or a Benchmark condition drops the changes. "Prender todo" drops everything.
- **Assistant.** A `prepare_scenario` result sets the map's point, changes and failures, paused at 0 (`useAssistant(s, onScenario)`, `scenarioOf()`). The chat stays open beside the map (before, the view jumped to the tabs and hid the reply).
- **Pins.** Each change that adds demand or generation (`add` over 0) at one to five substations gets a pin at each substation the prepared grid reports (`placed.ts`, drawn in `MapOverlays`): "+120 MW de demanda · S/E ANTOFAGASTA". A plant is a disc in its technology color (`TECH_COLORS`), a load a white ring. "Estado de la red" lists the change with "en S/E …".
- **Shared sessions are hidden from the web for now** (#101). There is no rail button, `?sesion=` is ignored and the assistant no longer joins its session. The session code stays in place, inactive.
