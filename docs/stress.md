# Prepared scenarios (stress)

A prepared scenario changes the grid before any failure: more people in a place, more demand, less generation of a technology, weaker lines. `POST /api/v1/grids/prepare` only prepares it. It never runs the cascade. A failure on the prepared grid runs in the existing processes, which take the same `changes`: `POST /grids/simulate`, `/grids/dependency` and `/grids/cost`.

Nothing is stored. The client keeps `changes` like it keeps the cuts and sends them with every request. Loading a scenario or a benchmark starts clean. Several changes apply together, in order. There is no cooldown.

Code: `backend/src/cascadasen/application/grid_stress.py`, bodies in `api/stress_schemas.py`, routes in `api/grid_routes.py`.

## Change

```json
{"target": "population", "comunas": ["Puente Alto"], "factor": 2}
{"target": "demand", "zones": ["NG"], "add": 200}
{"target": "generation", "tech": ["hidro"], "factor": 0.5}
{"target": "lines", "kv": [220], "factor": 0.8, "x_factor": 1.1}
```

| target | value | filters |
|---|---|---|
| `population` | people; demand follows | `comunas` (CUT or name), or `buses`, `zones`, `areas` |
| `demand` | MW, population unchanged | `comunas`, or `buses`, `zones`, `areas` |
| `generation` | MW | `buses`, `zones`, `areas`, `tech` |
| `lines` | capacity (`factor`), reactance (`x_factor`) | `lines`, `kv`, `zones`, `areas` (both ends inside) |

- `factor` multiplies each element (0 to 5). `add` is one total for the filter, split by the current value, or evenly when every value is zero. Use one of the two. Lines take `factor`, `x_factor` or both.
- Filters combine: every given filter must hold. No filter means the whole country.
- Zones: `NG`, `NC`, `CE`, `CS`, `SU`. Areas: `A01` to `A13`.
- `tech`: `hidro`, `solar`, `eolica`, `bioenergia`, `geotermica`, `carbon`, `gas`, `diesel`. `termica` is a tag for `carbon` + `gas` + `diesel`.
- Limits: 20 changes per request. The overlay limits still hold: 5,000 MW changed in total, 3,000 MW per bus. Over a limit the API answers 422.
- A value is never pushed below zero. A base load that is already negative (net injection of embedded generation: 28 buses at feb2025-1500, 27 at nov2026-1300) stays as it was. The overlay now accepts `load_mw` down to `min(0, base)`.

## Demand per person

`ΔMW = Δpeople × s_reg × demand_total(point) / people_total`, with `s_reg = 0.389` (`cascade.yaml` `stress.regulated_share`).

- Free clients (mining, industry) used 61.1 % of the SEN in 2024 (Coordinador Eléctrico Nacional, via Enel X). They do not grow with population. The regulated part (homes, commerce, small firms) does.
- Per point: 238 W per person at feb2025-1500, 187 at feb2025-0300, 232 at nov2026-1300 and 234 at nov2026-2000.
- Why not scale each bus's load by its people: load per person is 1,826 W in Norte Grande and 522 W in Centro-Sur, and the top tenth of buses is over 35 kW per person (mines). Doubling the people near a mine would double the mine.
- Check: residential use alone is 778 kWh per person per year, about 89 W on average (CNN Chile). The regulated value also holds commerce and small firms.
- **Assumption:** the same value per person everywhere.

## Generation by technology

The dispatch comes summed per bus (`baseline_opf.json`). Each bus's generation is split by technology in proportion to its plants' installed MW times the national dispatch factor of that technology at the point (`gen_by_carrier_mw` over installed MW). Thermal plants are split by their first fuel: carbón and petcoke go to `carbon`, natural gas and propane to `gas`, petróleo and fuel oil to `diesel`. Cogeneration and "S/I" (22 MW) count only under `termica`, with no dispatch. **Assumption.**

Synchronous technologies (hydro, thermal, bioenergy, geothermal) move their synchronous MW with them, and inertia scales with it, capped at the overlay's 10 s.

## Redispatch

The overlay's rule is unchanged: the island's synchronous base units take the imbalance, weighted by their synchronous MW. Buses whose generation the scenario sets take no share. There is no upward capacity limit. The grid tries to survive, and what breaks is the lines.

## Responses

`POST /grids/prepare` (agent route `prepare_scenario`):
- `changes`: per change, `matched`, the deltas, and `elements` with each value before and after.
- `totals`: people, demand and generation of the prepared grid.
- `overloaded_lines`: lines over the cascade's limit with no failure. A simulation starts with them.
- `should_feed`: per generating substation, by id, and per zone, the people it should feed.
- `redispatch`, `warnings`, `assumptions`.

`POST /grids/simulate` with or without `changes` adds `supply`. For each generating substation it gives `should_feed` (on the prepared grid before the failure), `feeds` (once the cascade settled) and `pct_fed` (percent). People at a substation out of service count as not fed. `by_zone` adds the same up per zone. A simulation still needs at least one cut or substation out.

Percentages carry 2 decimals. Sources are ordered by id, never by damage (`docs/cyber.md` section 8.2). The assistant tool gets only the per-zone stat.

## Web map

- **Edit in place.** The card of a selected substation has factors for Personas, Demanda and Generación. The card of a line has one for Capacidad. A factor applies on Enter or when the field loses focus, and 1 removes it. Each one writes a change for that component alone (`{"target": "population", "buses": ["B062"], "factor": 2}`), kept with the cuts in `Edits.changes` (`web/src/cascade/edits.ts`, also in localStorage).
- **Batch changes only from the assistant.** Changes by filters (zones, technologies, comunas) come from the assistant. The person edits one component at a time. "Estado de la red" lists every change, with "Quitar" on each.
- **Simulation.** With changes, the web never reads the precalculated cache: `/grids/simulate`, `/dependency` and `/cost` get `changes`. With changes and no failure, the map shows the base case, and the panel shows the prepared grid from `/grids/prepare`: totals, lines already over their limit, and the prepared values in the card. "Simulación" shows `supply` per zone, and a generating substation's card shows its own numbers.
- **Reset.** Opening a disaster or a Benchmark condition drops the changes. "Prender todo" drops everything.
- **Assistant.** `prepare_scenario` sets the final grid of the map: point, changes, lines out and substations off. It replaces what was on the map. With failures the tool also simulates (people without power with and without the changes, supply per zone), and the map loads the timeline paused at 0. The user presses play. The tool needs no session.
- **Shared sessions are hidden from the web for now** (#101). There is no rail button, `?sesion=` is ignored and the assistant no longer joins its session. The session code stays in place, inactive.

