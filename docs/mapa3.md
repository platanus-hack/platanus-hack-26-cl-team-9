# Mapa 3: cascade viewer

Mapa 3 is the main map of the app (`/`, also `?mapa=3`). Mapas 1 and 2 (`?mapa=1`, `?mapa=2`) are deprecated and kept as reference. Mapa 3 shows what happens to Chile's SEN when you cut a transmission line. You click a line, the engine (`docs/engine.md`) computes the cascade, and the map replays it stage by stage: lines that overload and open, islands that form, substations that go dark, and the frequency of each island.

UI strings are Spanish. This document is English. Every claim is tagged EVIDENCE (read from code, data or engine output) or ASSUMPTION (a modelling choice, not verified against the real system).

![Base case](images/mapa3-base.jpg)

## 1. Actors in the network

This is the reference list for future work. Each actor has: what it is in our data, what role it plays in the cascade, how the map draws it, and where it lives in the code. "Modelled" means the engine computes something with it.

### 1.1 Summary table

| # | Actor | Modelled | Role in the cascade | Drawn on the map |
|---|---|---|---|---|
| A1 | Substation (bus) | Yes | Node where generation, demand and lines meet. Becomes dark when its island collapses. | Circle. White = energised, red = dark, bigger = 500 kV |
| A2 | Transmission line | Yes | Carries power between two substations. Opens when it exceeds 120% of capacity, or when you cut it. | Line. Colour = loading, width = kV |
| A3 | Synchronous generator | Yes (aggregated per bus) | Supplies MW, supplies inertia (slows frequency change) and primary reserve. | Not drawn |
| A4 | Non-synchronous generator (solar, wind, CSP) | Yes (aggregated per bus) | Supplies MW, no inertia, no reserve. Is curtailed when frequency rises above 50.2 Hz. | Not drawn |
| A5 | Demand (load) | Yes | Consumes MW. Falls slightly with frequency. Is the thing that gets shed. People in the dark are computed from it. | Blue rectangular bar |
| A6 | Overload protection | Yes (simplified) | Opens the most overloaded line(s) each stage. | Line turns grey and thin ("open") |
| A7 | EDAC (under-frequency load shedding) | Yes | Disconnects demand in steps when island frequency falls. | Events list, frequency chart, shorter bars |
| A8 | Island | Yes (emergent) | A group of substations still connected to each other after cuts. Has its own frequency. Survives or blacks out as a whole. | Colour of its frequency curve in the chart |
| A9 | Attacker or fault (the user's second click on a selected line or substation, "Sacar de servicio" or "Apagar subestación") | Yes | Starts the cascade by opening a line, or taking a substation out of service, at t = 0. | Cut line drawn dashed gray ("fuera") |
| A10 | Transformer | Folded away | Not an actor in the engine. Its capacity is merged into the line. | Not drawn |
| A11 | HVDC link | No | Excluded. Kimal-Lo Aguirre is a 2029 build, so it is dropped for 2025 and 2026. | Not drawn |
| A12 | Storage (batteries, pumped hydro) | No | Not modelled as fast injection. | Not drawn |
| A13 | System operator (CEN) | No | No manual redispatch, no restoration. | Not drawn |
| A14 | Voltage and reactive power | No | DC flow only. The north's voltage collapse in the real 25F is not computed. | Not drawn |
| A15 | Distribution companies and customers below 66 kV | No | Only their aggregated demand at the substation. | Not drawn |

### 1.2 Detail per actor

**A1. Substation (bus).**
- Data: `NetNode` in `web/src/cascade/types.ts`: `id, name, lon, lat, kv, zone, map_nodes`. 188 in the 2025 and 2026 networks (EVIDENCE: `network-2025.json`).
- Rule: one bus per substation. The 1,930 lines and the transformer buses of the PyPSA-CL model collapse into it (`network.py`, `reduce_network`).
- Zone: `norte_grande` if latitude is north of -26.0, otherwise `centro_sur` (EVIDENCE: `NORTE_GRANDE_MAX_LAT`). The zone selects which EDAC table applies.
- State per operating point (`buses.json`): `gen_mw`, `load_mw`, `people`.
- Becomes dark when its island ends as `blackout`, `dark` or `local_cut`.

**A2. Transmission line.**
- Data: `NetLine`: `id` (for example `R239`), `a`, `b`, `kv`, `capacity_mw`, `x_pu`, `map_edges`, `branches`.
- 273 lines. Parallel circuits and transformers between the same two substations are merged: capacity is added, reactance is put in parallel. A click on a line cuts the whole merged corridor (for example the four 500 kV circuits Alto Jahuel-Ancoa).
- Reactances under 5e-4 pu are raised to 5e-4 pu (ASSUMPTION, keeps the solver well conditioned).
- Per stage state: `flow_mw`, `loading` (flow / capacity), `status` = `ok`, `overload` or `open`.
- Drawn as a straight segment between the two substations, not the real route.

**A3. Synchronous generator.** Hydro (reservoir and run-of-river), coal, gas, diesel, biofuel, geothermal.
- Role: gives MW, rotating inertia (`inertia_by_bus_mws`) and primary reserve.
- Primary reserve = 4% of the online synchronous MW of the island, full at 0.3 Hz deviation, time constant 3 s (ASSUMPTION, `frequency.py`).
- Inertia is what slows the frequency fall. An island with no synchronous machine cannot hold frequency and is lost (`no_inertia`).
- The engine holds one aggregated value per substation, not per plant. Plant-level detail exists in `operating_points.json`.

**A4. Non-synchronous generator.** Solar PV, onshore wind, CSP (EVIDENCE: `NON_SYNCHRONOUS` in `build_baseline_opf.py`).
- Role: gives MW. No inertia, no reserve.
- Over-frequency: reduced by 55% of its power per Hz above 50.2 Hz (NTSyCS, per `frequency.py`).
- Ride-through trips (inverters disconnecting on voltage or frequency dips) are not modelled. In the real 25F they mattered.
- This is why the hour matters (EVIDENCE: `baseline_opf.json`, MW by carrier):

| Point | Solar PV | Wind | Hydro (ror + reservoir) | Coal | Gas |
|---|---|---|---|---|---|
| feb2025-1500 | 5,944 | 1,447 | 2,818 | 94 | 423 |
| feb2025-0300 | 0 | 1,337 | 4,331 | 2,008 | 693 |
| nov2026-1300 | 7,706 | 1,606 | 1,300 | 60 | 2 |
| nov2026-2000 | 0 | 7,510 | 2,017 | 719 | 355 |

**A5. Demand.**
- Source: PyPSA-CL `Loads.xlsx`, mapped to the 188 substations. People come from the INE comunas served by each node.
- Frequency dependence: load changes 1.5 % per Hz (ASSUMPTION, range 1 to 2 %/Hz in `stack.md`).
- It is lost in two ways: shed by EDAC (a share of the zone's load), or lost with its island.
- Drawn as a rectangular bar of 90 m per MW (exaggerated), only for substations above 20 MW (92 of 188 at `nov2026-1300`).

**A6. Overload protection.**
- Each stage, the engine computes DC flows. If the worst line is above 120% of capacity, it opens every line at that worst ratio (ASSUMPTION: 120% threshold, 1.0 s between stages, up to 20 stages).
- Its parameters are in `Params` in `engine.py`. It is a simplification of real line protection (no time-current curves, no thermal inertia).
- N-1 is not imposed in the base case, so some lines start at 100% of capacity and any extra flow trips them.

**A7. EDAC.**
- Real steps taken from the CEN 25F report: centro-sur table (6 steps from 49.0 to 48.3 Hz, per zone, with a rate-of-change trigger on steps 1 and 3 at -0.6 Hz/s) and norte grande Tabla 3-9 (step 1 disabled).
- MW per step are interpolated between the low-demand and high-demand columns by system load (8.5 to 11.5 GW, ASSUMPTION) and then scaled to a share of the island's own zone load. A small island sheds less.
- Each step fires once.

**A8. Island.**
- Found by walking the lines that are not open (`flow.py`, `find_islands`).
- For each island the engine solves the swing equation `(2E/f0) df/dt = P_gen + P_reserve - P_curtailed - P_load(f)` for 20 s.
- Outcomes: `maintains` (frequency stays between 47.5 and 52 Hz), `blackout` (leaves that band), `dark` (no generation or no load), `local_cut` (no inertia and under 200 MW load).
- A balanced island (gap under 1 MW) is stable without simulating.

**A9. The cut.**
- Any line or substation. Without a session the changes add up in the Cambios tab (a substation goes out with its demand and generation); in a session several lines can be open, and switching off a substation opens every line that touches it. The engine accepts several ids (`run_cascade_workflow`).
- Real-world meaning: a physical attack, a fault, or a maintenance outage. The engine does not distinguish.

**A10 to A15. Not actors in this version.** See section 7. These are the first candidates to add, in this order of value: voltage collapse in the north (A14), ride-through trips (A4), storage (A12), HVDC (A11), N-1 base case, operator actions (A13).

### 1.3 Who acts at each moment of a cut

| Time | Actor that acts | What happens |
|---|---|---|
| 0.0 s | A9 cut | The line opens. |
| 0.0 s | A8 islands | The engine looks for islands. |
| 0.0 to 20 s | A3, A4, A5, A7 | In each island: inertia slows the fall, reserve and damping push back, EDAC sheds load by steps. Outcome: maintains or blackout. |
| 1.0 s, 2.0 s... | A6 protection | The most overloaded line opens. New islands may form. |
| End | A1 substations | Those in islands that collapsed become dark. People are added up from A5. |

## 2. Quick start

```bash
git pull
cd backend && PYTHONPATH=src python -m cascadasen.application.cache_builder   # or: uv run cascadasen-cache
cd ../web && npm install && npm run dev
```

The cache (about 46 MB, 4 hours x (273 line cuts + 188 substation shutdowns + `health.json`)) is committed, because the deployed web image has no Python. Regenerate it with `cascadasen-cache` and commit it whenever the engine or `data/processed` change. If a file is missing the page shows "Faltan datos de la simulación en esta versión de la app." and the browser console names the file (`/cache/...`) and says to run `cascadasen-cache`; a failed read is asked again on the next try (`web/src/cascade/api.ts`).

| URL | Opens |
|---|---|
| `http://localhost:5173/` | Base case, Nov 2026 13:00 (same as `?mapa=3`) |
| `/?mapa=3&point=feb2025-1500` | Pick the hour: `feb2025-1500`, `feb2025-0300`, `nov2026-1300`, `nov2026-2000` |
| `/?mapa=3&point=feb2025-1500&cut=R239` | The 25F corridor cut, already playing |
| `/?cut=sub-B012` | Substation B012 out of service, already playing |
| `/?pais=PER` | Peru's network, framed (also `ARG`, `BOL`, `BRA`; view only, section 4.1) |

The URL follows the app: choosing a point or making a change rewrites `point` and `cut`, so the address bar is a deep link to the current view. It carries only values that differ from the defaults: a point other than `nov2026-1300`, one change as `cut` (a line id, or `sub-<bus id>` for a substation shutdown) and `pais` for a network other than Chile's (an uploaded network is not written: it exists only in that browser). Two or more changes, or a prepared scenario, are not written (`urlCutOf`). Other params (`sesion`, `mapa`, `limite`) are kept; an old `vista` param is dropped. A bare `/` is the default view, and an explicit `?point=nov2026-1300` is normalised to `/` (`web/src/cascade/url.ts`).

Bad links never hang or fail silently (2026-11-22): `?point=` with an unknown id opens the default point with the notice "No existe la condición «xxx». Se muestra Mediodía solar." and the URL is normalised; `?cut=` naming a line or substation the network does not have opens the network without changes and says "No existe la línea «R999» en la red. Se muestra la red sin cambios."; `?pais=` with a country the build has no network for opens Chile with "No hay una red disponible para «XXX». Se muestra Chile.".

**Saved changes.** The changes are saved in this browser (`localStorage`, `sub50.edits.v1`), but they come back on load only when the URL describes them. A bare `/` always starts clean, so a previous visitor's cut never shows up (F-14). When the browser holds changes the URL does not describe, a notice says how many and offers **Restaurar**; the first new change replaces them. Code: `startEdits` in `web/src/cascade/edits.ts`.

With `VITE_MAPBOX_TOKEN` in `web/.env.local` (git-ignored) the basemap is Mapbox. Without it, the offline Chile outline is used.

## 3. Map view (2D only)

The map is 2D only (the 3D view was removed on 2026-11-22, issue #115). It uses the Mapbox Standard map (night, monochrome theme) with the land painted flat gray by a fill layer of the app (`web/src/map/baseMap.ts`; `docs/design.md` section 7 says why) and matches Design v5: the camera looks straight down and cannot be tilted or rotated. The layers button (top right, above zoom) opens a small panel with the layer switches. The map controls also have **Ver toda la red**, which returns the camera to the frame of the network on the map. Escape or a click outside closes the layers panel. To the left of the layers button, on the same row, is **Prender todo** (section 4, item 9); the open layers panel covers it. The layer switches are **Flujo de potencia** (moving dots, on by default) and **Demanda por subestación** (off by default): cream discs whose area grows with MW.

## 4. How to use it

Layout (Paper "Design v5", `docs/design.md` section 3.2, with the Design v6 rail and line colors of section 3.3): a 200 px nav rail, a 440 px panel docked next to it with three tabs (**Simulación**, **Red**, **Cambios**), the timeline card under the panel while there is a timeline to play, map controls at the top right, and the legend with the scale bar at the bottom right.

**Cold start.** A bare `/` opens on **Simulación** with line colour Carga. With nothing cut, its first card is "¿Qué pasa si se corta una línea?": one sentence on how to cut, a search field "Buscar una línea o subestación" (a datalist of every line and substation by name; choosing one selects it on the map and opens its card, the keyboard route to the core task; `web/src/cascade/search.ts`), the primary button **Ver el apagón del 25 feb 2025** and the line "Red resumida con datos públicos. Las cifras son estimaciones del modelo, no una predicción.". The pre-fault index and the N-1 money at risk sit under the closed disclosure **Indicadores técnicos** ("Margen de la red", "Costo esperado si falla una línea cualquiera", "Costo si falla la peor línea"). There is no timeline card and no **Prender todo** until something is off.

**Autoplay.** Playback starts by itself at 1x from 0 s when a new timeline arrives after a cut or a shutdown made by the user, a Desastres entry, a `?cut=` link, or another operating condition picked while changes are in force. It stays paused after **Prender todo**, after a restore to the base case, after **Restaurar**, after an assistant scenario, and when the browser asks for reduced motion (`prefers-reduced-motion: reduce`). Opening the Desastres entry already on the map replays it from 0. Code: the `autoplay` ref and `_arrived` in `CascadeApp.tsx`.

**Line colour follows the tab.** Red is Tensión, Simulación is Carga, Cambios keeps what is on. A choice made in the legend lasts until the next tab change or scenario open. A network other than Chile is always drawn in Tensión.

1. **Nav rail.** Order: **Mapa**, the **Escenarios** section label (Roboto Condensed 12/16, muted, not a button) with its tree, **Incidentes**, **Ciberataque**, **Asistente**, then at the bottom **Redes disponibles**, **Fuentes y supuestos** and **Ayuda**. One navigation row is highlighted at a time: **Mapa** (with `aria-current`) only while no other rail view is open. The active operating condition keeps its own fill (it is data, not navigation); while a view-only network is shown, no Chile condition is highlighted. The whole rail scrolls when the window is short. **Escenarios** has two folders. **Desastres** holds real events (`DISASTERS` in `Scenarios.tsx`, each an operating point plus the changes it applies, simulated through `POST /api/v1/grids/simulate` when it is more than one line):

   | Entry | Point | Changes | Model | Real event |
   |---|---|---|---|---|
   | Apagón 25F | `feb2025-1500` | cut `R239` (Nueva Maitencillo – Nueva Pan de Azúcar 500 kV) | 18.2 M people, 11,096 of 11,096 MW | about 19 M (98.5 %) |
   | Apagón 2011 · Ancoa | `nov2026-2000` | cut `R006` (Alto Jahuel – Ancoa 500 kV) | 3.2 M people, 2,118 of 10,934 MW, 5 stages | 24 Sep 2011, 9.8 M people, Coquimbo to Maule; a 500/220 kV transformer failed at S/E Ancoa ([Wikipedia](https://es.wikipedia.org/wiki/Apag%C3%B3n_de_Chile_de_2011)) |
   | Terremoto 2010 · Charrúa | `nov2026-2000` | S/E Charrúa (`B043`) out of service | 4.1 M people, 2,410 of 10,934 MW, 2 stages | 14 Mar 2010, more than 13 M people, the whole SIC; a transformer damaged by the 27F earthquake failed |

   ASSUMPTION: 2011 and 2010 are analogues on today's network at the closest hour we have (the 2026 evening peak), not reproductions: the reduced network folds transformers into lines, the post-earthquake damage is not in the repo, and the 2010 SIC was not joined to the north. Measured 2026-11-22. Issue #35 lists how to bring Charrúa closer to the real event. Each entry shows the date of the real event (25F: "25 feb 2025 · 15:16", `docs/idea.md`), and its name may wrap to two lines. While an entry is on the map the impact card shows the real figure under the model's: "Evento real: unos 19 M de personas (98,5 %)"; for 2011 and 2010 "Análogo en la red de 2026. Evento real: 9,8 M de personas" and "… más de 13 M de personas", with the source in the info tip (`Disaster.real` in `Scenarios.tsx`). The cuts the user makes are not scenarios: they go to the tab Cambios. **Condiciones de operación** (the row reads "Condiciones": the full name does not fit the 13 px row; it is the accessible name) holds the operating conditions with no cut, other than the 25F's own point: "Demanda mínima", "Mediodía solar" and "Punta nocturna", each with its date. A Desastres entry replaces the changes, opens Simulación and plays. A condition keeps the failures and the open tab, and plays the cut again at the new hour when failures are in force; the rail then highlights that condition (even if the kept changes match a disaster) and says "Con N cambios tuyos" under it. A bare `/` opens Mediodía solar with Chile alone. A cut on another hour is made by picking a condition and cutting a line on the map. If the cache has no timeline for that cut at the point, the app shows the base case and a note. Code: `web/src/cascade/Scenarios.tsx`; the names and date lines come from `conditionName` and `conditionDate` in `text.ts`. **Redes disponibles** (it was "Fuentes de la grilla") picks, from the documents the backend stores, the one network on the map (docs/grids.md, section 4.1); a failed catalog read shows the error with **Reintentar** and is tried again when the list is reopened.
2. **Nav rail, other items** (2026-11-22, UI fix plan WP3 item 2): **Ayuda** opens with one sentence on what Sub50 does, "Cómo se usa" as four numbered one-line steps (pick a line or substation, Sacar de servicio plays the cascade by itself, read Simulación, try another hour in Condiciones or go back with Prender todo), one muted line with the search field, the second click, the space bar and Desastres, then "En el mapa" (line colour follows the tab and the legend card explains it; flow dots, substations with and without supply, demand discs, event numbers), the other countries' block when one is shown, and a "Glosario" (isla, corte automático de carga (EDAC), N-1, MW, frecuencia). It no longer repeats the line colours of the map legend. **Fuentes y supuestos** opens with three plain lines (a reduced network from public data; hourly generation and demand are simulated; the figures are model estimates and each (i) says where a number comes from), then the sources as a list, each linked when `docs/datasets.md` section 7 has its address (IDE Energía, Infotécnica, PyPSA-CL, INE Censo 2024, the Coordinador's 25F report, the CNE failure cost, Mapbox; the Sub50 engine and the BCN or geoBoundaries outlines without a link), then the engine assumptions as rows: each shows its own label ("Flujo DC"), its first sentence or its first words, and opens to the whole text ("Ver más"). Doc references in the assumptions read "(supuesto del modelo)" (`plainAssumption`, `assumptionTitle` in `text.ts`). The disabled "Validación" placeholder was removed from the rail (2026-11-22).
3. **Tab Red**: size of the whole IDE Energía grid (km of lines, substations, installed MW, km by voltage band). Line colour shows voltage. The three files are read once per page and kept (`loadNetworkSummary`), so the tab never renders empty: a loading card shows the first time, and a failed read says so with **Reintentar**.
4. **Select and cut.** A single click on a line or a substation selects it at once (white halo on a line, larger outlined dot on a substation) and its card opens at the top of the panel, in whichever tab is open; selecting never switches tabs or the line colour, and it leaves Ayuda or Fuentes. Clicking empty map or pressing Escape clears it. Lines are picked within 10 px of the pointer, and a click that also reaches the selected element goes to it, so a second click on the selected line never loses to a nearby substation dot. A **second click** on the selected element switches it off, the same as the button in its card; a fast double click (two clicks on the same element within 400 ms, or the browser's double-click event) never switches anything off, so a double click on an unselected element only selects it. A double click on an element that is already selected switches it off on its first click, because that click is itself the second click. Switching back on is only from a card, and a second click on something already off does nothing. Map tooltips say "Clic para ver el detalle", and on the selected element "Clic otra vez para cortarla" / "Clic otra vez para apagarla"; a line that is off reads "Fuera de servicio · clic para ver el detalle". Each card reads top to bottom: its figures, the action button, the lists, and last a closed disclosure **Modificar valores** with the factor fields and their explanation (open while a factor differs from 1). The factor fields apply on Enter or blur; a blank or out-of-range value keeps the previous factor and says why next to the field (0 to 5, and over 0 for a line's capacity, the backend's bounds; `parseFactor` in `edits.ts`). The line card shows voltage, the model circuits folded into the corridor ("1 circuito del modelo", "N circuitos del modelo fundidos en uno": not physical circuits), capacity, flow, loading with a bar across the card in its load band colour, the flow's direction and status at the current second (en servicio, sobrecargada, fuera de servicio, sin tensión; a line exactly at 100 % reads "al límite"), the button **Sacar de servicio**, and its two end substations (a click selects them). No tip names a file or an endpoint. The cut line's card and the impact card offer **Volver a conectar** (**Volver a conectar todas** for several lines), which returns to the base case at the same point. A cut clears the selection and switches the panel to **Simulación** and line colour to load, so the impact card is at the top. The substation card shows kV, zone, generation, demand, people and its connected lines with their loading; a click on one of those lines selects it. Its button **Apagar subestación** (or a second click on the selected substation) takes it out of service with its demand and generation; it is one more change in the Cambios tab, simulated together with the others through `POST /api/v1/grids/simulate` (docs/grids.md). In a session it opens that substation's lines instead (section 11). A link `?cut=sub-B012` opens with that substation out of service, and a single shutdown is written to the URL that way. While it is out, its card and the impact card offer **Volver a encender**; its lines are not off by themselves. The cache still holds `<point>/sub-B###.json` (every line of that bus opened at t = 0, built by `cascadasen-cache`); the app no longer reads it. How clicks arrive on each basemap: `web/src/cascade/clicks.ts`.
5. **Tab Simulación**: people without supply and their share of the country (both from the same bus data: the headline never exceeds the people the buses hold), lost load, lost generation, the frequency, and the numbered event history right under the impact card. The frequency is the lowest live island's; when every substation is dark at second t it reads "apagón" in the fault colour, never "50,00 Hz", and when the engine darkened the islands by the voltage rule its caption reads "colapso por tensión (regla del modelo)" (`systemFrequency` in `simulation.ts`). The icon button in the card header copies the page URL and confirms "Enlace copiado"; it shows only when the URL describes the view (one change) and never in a session. When the cascade has played out and the engine found nobody without supply and no lost load, the card says "El sistema resiste este corte" instead of a large 0 (204 of the 273 cuts at `nov2026-1300`). Every figure is read at the current second of the timeline, so it grows as the cascade plays (section 5.1). A click on an event jumps to it, and that row stays the current one while the time does not move, also when several events share the second. The current row is kept in view inside the card and, when the card runs below the panel, in the panel. The "N supuestos en esta simulación" row opens the assumptions. Below the figures, under the small heading "Al final de la simulación" (issue #72, `health.md` "Cost"): the after-cut "índice de margen operativo" and the "costo estimado" in US$ (with a note when the voltage-collapse rule darkened islands), captioned with the hours that cost really uses and whether they are calibrated or assumed ("…, con 7,34 h calibradas de corte." for a blackout, "1 h supuesta" for load shed; `hoursText` in `text.ts`); these two are end values, not animated with t. Without a cut, the cold start card (above) shows the pre-fault index and the N-1 money at risk (expected and worst) from `<point>/health.json` under "Indicadores técnicos", hidden in a session or a composed grid. Each row hides when an old cache lacks its fields. When the engine reached its 20-stage cap (`truncated`), the impact card says "La cascada se cortó en N etapas (límite del motor); podría seguir." (once). When the server simulation of several changes fails, the panel says "No se pudo conectar con el servidor." (or the server's Spanish message, without the developer notes in parentheses, `errorText`) with **Reintentar**; the timeline card leaves its loading state, and **Prender todo** or **Reponer** still recover. While a simulation loads or after it failed, the map keeps drawing the last frame it had (the base case on a first load), so the lines never vanish. With an incident or cyber cascade on the map and no cut of the user's, Simulación shows that cascade's impact card and history like a cut's, and the card's last row says whose cascade it is ("El mapa muestra la cascada del incidente «…», ciclo N.") with **Volver al incidente** (or **Volver al escenario**) and **Quitar del mapa**. An incident cascade and a cyber cascade never mask each other: the one that starts last takes the map, and a cut or a shutdown removes either.
6. **Timeline card**: shown only while there is a timeline to play (a change, or an incident or cyber cascade on the map); otherwise the panel takes its height. Clock with tenths, the frequency of each island (each island has its own stroke pattern on the curves and a matching swatch in the readout; with three or more islands the readout wraps onto two lines and names them in its tip), speed (1x, 2x, 4x, a segmented control), play, pause or repeat, and the rail. The clock and the position both round down to tenths, and the playhead stays visible during a cascade. The rail spans the whole timeline (`duration_s`) on a non-linear scale (`timeWarp` in `simulation.ts`, issue #90). Each instant that cuts, opens or darkens something (and the last load shed) gets at least 1.5 s of track and room for its own marker (30 px). Long quiet gaps keep their real length, and the tail after the last event with an effect (most of it the 20 s transient) is squeezed to about 15 % of the rail. Events at the same instant share a marker ("3–10"). A cut, an opening, a new island or a blackout never joins an earlier instant's marker, while EDAC steps and stable islands join the marker before them when they would overlap it. Play advances in track time, so the simulation slows down near each failure without pausing and runs fast through the tail. The clock and the position still read simulated seconds. With 9 or more such instants (5 of the 1,848 cached cuts) the markers are packed side by side. The curves above the rail are the island frequencies on a fixed scale (y = 11 - 4 x (Hz - 50) in 22 px), drawn up to the current second; red means the island fell below 49 Hz. Drag the rail, click a marker, or use the arrow keys (0.1 s of track, Shift for 1 s), Home and End. The space bar plays or pauses when no form control or button has focus. How to start a cut is said only by the cold start card.
7. **Map pins and callout**: the same event numbers appear on the map where the event happens (the cut or tripped line, the centroid of the zone that sheds load, the centroid of the area that goes dark). The latest event with a place is red and has a callout with people without supply and lost load, which **Cerrar** hides until another event becomes current or a pin is clicked. The callout is docked at the top gap right of the panel, 300 px wide (narrower when the map area is), and a 1 px #D0D1D4 leader joins it to its pin (`_placeLeader` in `CascadeApp.tsx`); while the layers popover would cover it, the callout and its leader hide. The first event keeps a short one-line label (12 px, at most 200 px) once another event is current, hidden when it would cover another pin. Pins that would overlap on screen are moved right, side by side, so a group never covers or steals the clicks of another pin. Events without a place (an island forms, an island stabilises) appear only in the history and on the rail.
8. **Legend** (bottom right): "Color de líneas" switches between Tensión and Carga with a segmented control (no native select). The Tensión legend lists only the voltage tiers in the model network; the Carga legend always lists six items and dims the ones absent from the current frame ("sin tensión" keeps its outline when dimmed). While a cut plays, "recién sin suministro" is one more cell of the same grid, with a 10 px ring. While a heat map is on, the legend names it and shows its ramp from low to high, or "Calculando en el servidor…" while the dependency answer is pending (one request per grid key: dependency and criticality share it). The scale bar draws nothing before the camera exists.
9. **Tabs outside a session:** **Simulación** (first, the default), **Red** and **Cambios** (it was "Estado de la red"; it reads "Cambios · N" while N changes are in force). In a session: Simulación, Red and Datos. "Qué lo habría evitado" and "Validación" are not built yet and are not shown. **Cambios** starts with "Al final de la caída" (people without power and % of the country, MW lost, generation lost, islands that went dark: the same figures Simulación shows at its last second). Its cost row comes from the timeline's own summary (`failure_cost_usd`, `unserved_energy_mwh`, `outage_duration_h`, written by the cache and by `POST /api/v1/grids/simulate`); only a timeline without them asks `POST /api/v1/grids/cost`. It lists every change the user made (lines cut and substations out of service), each with **Reponer**, and **Reponer todo**. A new cut or outage adds to the list, never replaces it. A second click on a selected substation takes it out of service like on a line (a shared session keeps its own edits in Datos). With no change or one line the app reads the precalculated timeline from `web/public/cache`; with more it calls `POST /api/v1/grids/simulate` and plays the timeline it returns (docs/grids.md). Code: `web/src/cascade/{edits.ts,NetworkState.tsx}`.
10. **Prender todo** (top right, left of the map controls): one step back to the full, energised network. It shows from every tab and from Ayuda and Fuentes. It clears every cut, the selection and the notice, and puts the timeline at 0, paused. It clears the list in Cambios (lines and substations) and keeps the operating point, so the rail shows the condition of that hour and the URL drops `cut`. The tab and the line colour do not change. It is not rendered while nothing is off, edited, or playing an incident or cyber cascade; a selection or a timeline position alone does not bring it. Code: `web/src/cascade/powerAll.ts` (`canPowerAll`, `powerAll`). Session behaviour: section 11.

### 4.1 One network at a time: other countries and uploaded networks

Issue #49. The map draws **one network at a time**. The panel header names it ("Chile · Sistema Eléctrico Nacional") and is the selector: a click opens the list.
- **Countries:** Chile and every country with a drawn layer (`docs/regional.md`).
- **Redes subidas:** each one with its name, its country and **Quitar**.
- **Subir una red…**

**Redes disponibles** (rail) chooses the same way, with one choice, from the documents the backend stores (docs/grids.md). Choosing a network removes the previous one from the map. The camera flies to the new one. Code: `web/src/cascade/NetworkPicker.tsx` and the `networkId` state in `CascadeApp.tsx`; the catalog is `BUILT_IN` in `web/src/map/country.ts`.

- **Camera per country** (`web/src/map/countryBounds.ts`, `cameraTarget`). Nothing is written by hand: everything comes from the data.
  - The frame is the box of the network's own buses plus 4 %: Chile's reduced network, the other countries' `substations.geojson`, or the upload. It stops where the grid stops (Chiloé for Chile, not Cape Horn).
  - The area the camera may wander (`maxBounds` on Mapbox) is the box of the buses and of the country outline (`chile.geojson`, or the `shapeGroup` of `latam/outlines.geojson`), grown by its larger side (at least 8°). It is wide on purpose: Mapbox keeps the whole viewport inside it, and Chile is tall and thin.
  - The lowest zoom is the frame's zoom minus 1.5; the highest stays 13. So Brazil can zoom out much further than Chile.
  - The over-land check uses only the chosen country's outline. An upload has none, because its country is only declared.
  - The basemap's `BaseMap.setTarget` lifts the old limits, flies (1.2 s, `fitBounds` with the panel clearance) and sets the new limits when the camera lands. The first fit (page load or `?pais=`) jumps.
  - `web/src/map/countryBounds.test.ts` checks, for each of the five countries, that the frame holds every substation, that `maxBounds` holds the frame, and that over 90 % of the substations are on that country's land.
- **Only Chile's network is simulated.** The others are drawn at level L0 (`network-format.md` section 2: no reactance, capacity, demand or inertia). On those networks:
  - the Cambios and Simulación tabs and the Escenarios tree are disabled, with the tip "Esta red es solo para ver…", and the Red tab repeats it;
  - **Prender todo**, the timeline card, Chile's map legend and the event pins are hidden. Chile's changes (Cambios) are kept and come back with Chile;
  - lines are always drawn in voltage colours, and a compact legend at the bottom right lists the voltage tiers the network has and the plant technologies it draws (`RegionalMapLegend` in `MapLegend.tsx`). Plants are solid discs with a dark rim in their technology colour, none of them red (thermal is a grayish brown, `TECH_COLORS` in `web/src/map/layers.ts`);
  - the Red tab's view-only note has a **Volver a Chile** button;
  - `?cut=` is ignored, and the URL drops `cut` while another network is shown;
  - their elements are not clickable as cuts (layer ids `regional-*`); the tooltip names the publisher ("Fuente: Osinergmin GISEM", without the source's layer numbers), writes numbers in es-CL and ends "Red solo para ver: no se simula".
  - A shared session (one joined by an incident run, see section 11) is always Chile's, and the selector is locked there.
- **Red tab figures.** Chile keeps the IDE Energía figures. A country takes its figures from `latam/manifest.json` (`line_km_by_kv`, `counts.substations`, `plant_mw_by_tech`, `summaryFromManifest`): these are the reduced layer's numbers, so its km undercount (`regional.md` section 2). An upload computes them from itself (`summaryFromGrid`); a line without `length_km` counts its drawn length.
- **`country` field.** Every node and line of `network-<year>.json`, every feature of `data/processed/geo/*.geojson` and every record of `node_index.json` carry `country: "CHL"`. The frontend reads the field only through `countryOf` (`web/src/map/country.ts`), which treats a missing field as `CHL`, so an older cache still works.

**Uploading a network** (part C; panel view "Subir una red", `web/src/cascade/UploadNetwork.tsx`):
- The form asks for a file, a **required** country (ISO3 list, Spanish names from `Intl.DisplayNames`, `web/src/map/iso3.ts`) and an optional name.
- Accepted formats, one file each (`docs/network-format.md`):
  - a GeoJSON FeatureCollection in the regional schema v2: `LineString` lines with `a`, `b` and `kv`; `Point` substations with `kv`; `Point` plants with `bus` or `mw`;
  - the v1 network JSON with `buses`, `lines`, `dc_links` and `plants` (Brazil's `latam/BRA/network.json` is accepted as is).
- `parseUpload` (`web/src/map/upload.ts`) refuses the file with a list of what failed (up to 12 items, then "y N errores más"). It refuses:
  - a file over 10 MB (checked before reading it), or with more than 5,000 buses or 10,000 lines;
  - a file that is not JSON, or JSON of another shape;
  - a country that is not ISO3;
  - lat outside −90..90 or lon outside −180..180;
  - kv not a number or outside 1..1,500, or mw negative;
  - a missing or repeated id;
  - a line end that is not a substation of the file, or `a = b`;
  - a file with no substations.
- Each error sits under the field it belongs to: a missing file, the size and every check of the file under **Archivo** (a list when there are several), a missing country under **País**; the field is marked `aria-invalid`. The help text and the format error describe the two formats in plain words, with no file paths.
- If the file names another country, the form asks to confirm. The declared country is written onto every element.
- **Safety:** the file is read with `JSON.parse` only. Values are copied field by field into new objects. Text is cut to 120 characters, without control characters. Names reach the screen only as React text and through the deck.gl tooltip's `text` (never `html`). `upload.test.ts` covers the refusals, the country mismatch and a name with `<img onerror>` / `<script>`.
- **Storage:** IndexedDB in this browser only (`web/src/map/uploadStore.ts`, database `sub50`, store `uploaded-networks`); nothing is sent to a server. If the browser refuses to store it, the network still shows and a note says it will be lost on reload. Sharing it is for #34 / #44.
- An upload is never simulated (phase 2 would need the inputs of `docs/minimum-dataset.md`).

### 4.2 Documented incidents (Incidentes)

Continuation of issue #74 (`attack-sim.md` section 3.1). The **Incidentes** rail item (below Asistente) replays a public incident as a simulated scenario on Chile's network. It needs the backend.
- **Catalog:** one selectable card per incident from `GET /api/v1/attacks/catalog`, in the order of the file, never sorted by damage. The cards form a radio group (a square radio mark, arrow keys move the selection); the selected card has a 2 px white left rule and the selected background, and only it unfolds its effects and sources. Each card shows the title, the date ("26 ago 2026"), the hour it is simulated at ("simulado a las 13:00 del 1 nov 2026": a point is the 1st of its month) and a tag `no verificado` (press only) or `referencia, no es ciber` (25F). Effects name the operating areas (`GET /sim/catalog` → `cyber_attack.areas`, "Arica–Iquique"), corridors ("el corredor entre Vallenar y La Serena–Coquimbo") and macro zones ("la zona Norte Chico") instead of their codes. A source whose catalog label is a repository file (the 25F reference cites `docs/idea.md [3]`) is shown as the document it cites, "Informe del Coordinador Eléctrico Nacional sobre el 25F", with its public URL (`datasets.md` reference 3).
- **Options:** defence policy A/B/C and **Simular incidente** (primary button), in a block fixed to the bottom of the panel so they stay in view while the catalog scrolls. There is no outage-duration field: MWh and cost use the calibrated hours of the engine (section 4.2 "Result"). While a run is launching the cards and the policy are disabled and a second activation is ignored. A failed catalog shows "No se pudo conectar con el servidor." with **Reintentar**.
- **Own session:** an incident runs at its own hour (`operating_point`), and the API answers 422 when the session's hour differs. Without a session, or in one at another hour, the web creates a session at the incident's hour, labelled "Incidente: <título>", and enters it (asking first when it leaves another session). In a session at the same hour the run is added to it.
- **Flow:** `POST /{sid}/attacks/runs`, then `step` to the horizon (the snapshots), then the report and the after-action.
- **Result:** when the run ends the panel scrolls to the result card and moves the focus to its heading, and a `role="status"` line announces "Simulación terminada: <título>". The header says "Incidente simulado · política <the policy that was submitted, not the one selected now> · a las <hora>"; it shows no seed.
  1. Consequence card: level ("Absorbido", "Contenido", "Apagón regional", "Apagón nacional"), personas sin suministro, MW de carga perdida, and MWh and cost from the cascade engine, the same as the Cambios tab (25F: US$ 984 M, 81,443 MWh). The tips say how many hours of black start the dark load pays (7.34 h, calibrated with the 25F) and that load shed pays 1 h (supuesto); they name sources for people, with no bracket reference numbers. An absorbed incident (level L0, nobody without supply, no load lost) is titled "El sistema absorbió el efecto" and says so in one sentence instead of four zero figures.
  2. Agentic response from `report.indicators`, labelled "indicador experimental": time to understanding in cycles and minutes ("no se identificó en el horizonte", as text, when it never happened), mission continuity, unnecessary decisions, final reserve.
  3. "Qué lo habría evitado" ("Qué lo haría más robusto" for an absorbed incident).
  4. The cycles (`after_action.timeline`): the cycles with a cascade or a scenario effect are listed; the rest are folded behind "Ver los N ciclos". Backend text is made readable in the web (`plainText` in `incidents.ts`): area and zone codes by name, `edac:centro_sur` as "EDAC Centro-Sur", file names and bracket reference numbers removed.
  5. Notes and sources.
  6. Both notices: "Escenario hipotético: se modela el efecto, no el ataque." and "Consecuencia simulada en una red reducida, no una predicción."
- **Cascade on the map:** a cycle whose snapshot `transient` sheds load, darkens buses or opens lines can play on the map. When the run ends, the first such cycle plays by itself (`useIncident` sets `playing`; CascadeApp starts the timeline at 0 for an incident cascade). The result card says which cycle the map shows and has **Quitar del mapa** (or **Ver cascada en el mapa** after it was removed); each cycle with a cascade has its own button. The `transient` is a Timeline (same shape as a cut), so the timeline card, pins, callout and Carga colours play it like a cut. It takes priority over the session's own timeline. A double click cut, **Prender todo** (enabled while it plays), **Quitar del mapa**, **Cerrar incidente** or leaving the session remove it.
- **Not built:** a cycle-by-cycle viewer of `snapshot.grid`, the areas and the crews (section 10), injecting events from the web, comparing policies with replay.
- **Language:** "incidente simulado" and "escenario", never "atacar" or "hackear".

Code: `web/src/incidents/` (`incidents.ts` pure helpers, `useIncident.ts` state owned by `CascadeApp`, `IncidentPanel.tsx`).

### 4.3 Ciberataque

The **Ciberataque** rail item runs the `ciberataque` template (`attack-sim.md` section 3.2) in a fresh session at `nov2026-1300`. It needs the backend.
- **Form:** a short description (the threshold that closes the scenario is said as a share of the demand without supply), the defence as four buttons ("A · Reactiva", "B · Preventiva", "C · Adaptativa", "Comandante IA", disabled with its reason when the server has no language model), the primary button **Simular escenario**, then a closed disclosure "Parámetros (supuestos)" with the ten fields in an aligned grid (eight scenario parameters, field crews and the seed) and **Restablecer parámetros**.
- **Fields** keep what the user types (`texts` in `useCyber`); a field is checked against the catalog bounds when it loses focus and when **Simular escenario** is pressed, and the message sits next to it ("Espera entre saltos: entre 1 y 12 ciclos, sin decimales"). Cycles, crews and the seed are whole numbers; probabilities and shares are percentages and accept a decimal comma. While a field is invalid the button is disabled and the disclosure opens. One run at a time: a second activation is ignored.
- **Running:** the outcome card leads, titled "Ciclo 17 de 72 · simulando" with a progress bar; the description folds into "Cómo funciona el escenario".
- **Result:** the outcome titles say what happened to the network (D12): "La red perdió el umbral de demanda", "La defensa contuvo la intrusión y reparó todo", "Sin desenlace al terminar el horizonte", with one sentence that explains it, and take the focus. The first cycle with a visible cascade is shown on the map when the run ends, with **Quitar del mapa**. The cycle card has four model figures in a 2 by 2 grid with info tips (areas with intrusion, recovered areas, demand without supply, people without supply), busy crews as a line, and the areas with their name first and the code second; affected areas come first and healthy areas are quiet (no border, muted). The range input is drawn with the tokens.

Code: `web/src/cyber/` (`cyber.ts` pure helpers and form parsing, `useCyber.ts`, `CyberPanel.tsx`).

## 5. Legend (what the map draws)

| Element | Meaning |
|---|---|
| Line colour, Red tab | Voltage, in cold colors that get brighter with kV: 500 kV white, 154 to 345 kV light cyan, 100 to 110 kV blue, 44 to 69 kV deep blue, medium voltage gray |
| Line colour, Simulación tab | Loading at the current second, as a traffic light: under 50 % green, 50 to 75 % yellow, 75 to 100 % orange, over 100 % red and thicker. Red is always failure |
| Near-black line with a faint outline | "sin tensión": both ends are without supply |
| Dashed gray line | "fuera": cut by you or tripped by overload (over 120 %). Drawn above the live lines, so a cut line stays visible next to a parallel overloaded one |
| Line width | Always voltage: 500 kV, 154 to 345 kV, lower |
| Moving white dots | Direction of flow. Only lines with 60 MW or more |
| Substation dot | Light gray = with supply (larger: 500 kV), red with a dark outline = without supply |
| Red ring that grows and fades | The substation lost supply in the last 1.5 s of track time (at most 3 simulated s), so the current blackout stands apart from earlier ones. Legend: "recién sin suministro", shown while a cut plays |
| Cream disc or column | Demand of the substation (off by default) |
| Numbered pins | Events, the same numbers as the history and the timeline |

The map legend, the "Ayuda" view and the layers share the constants in `web/src/cascade/layers.ts` (`VOLTAGE_TIERS`, `LOAD_BANDS`, `DEAD_LINE`, `OPEN_LINE`, `FAULT`), so they cannot drift apart. The panel's "Líneas por tensión" card uses `VOLTAGE_BANDS` in `networkSummary.ts`, which takes its labels, kV limits and colors from `VOLTAGE_TIERS` and counts the whole IDE Energía grid rather than the 273-line model. The other countries' lines and substations (`web/src/map/regional.ts`) read the same `VOLTAGE_TIERS` and `NODE_COLOR`; in the load view their lines are neutral gray (`REGIONAL_NO_LOAD`) because they carry no load.

Not drawn: generation per plant, transformers, voltage and reactive power, networks below 66 kV, and the 1,930 original map lines of mapas 1 and 2.

### 5.1 Reading the cascade at second t

The cache stores one frame per network stage and events with their own times (`web/src/cascade/simulation.ts`):

- **Dark substations**: each `island_blackout` lists its buses (`ids`, issue #90), so they go dark at the event's own time, also when several islands of one stage go dark at different times. Buses that are dark in the last frame but in no blackout (a substation taken out of service) are dark from t = 0. A timeline whose blackouts carry no ids (an older cache) falls back to the frame rule: a frame's `dark` list appears at its first blackout.
- **People without supply and lost load**: dark substations count whole. Load shed in islands that survive is not stored per substation, so it is spread over time by the MW shed so far, and shed MW count at the system's people per MW before their island collapses. Both are capped by the engine summary, and from the last event on they equal it exactly (ASSUMPTION: the in-between values are an interpolation, not engine output).
- **Lost generation**: generation at dark substations. The engine has no generator trips.
- **Island frequency**: linear between the curve samples. An island whose curve stops at a blackout event shows "apagón".
- **Island names**: "Isla 1", "Isla 2" in the order the engine simulated them. The cache does not say which zone an island covers, so the app does not call them Norte or Centro-sur as the mockup does.

## 6. Worked example: the 25F corridor

![25F cut](images/mapa3-25f.jpg)

EVIDENCE (engine output, `feb2025-1500`, cut `R239` Nueva Maitencillo-Nueva Pan de Azúcar 500 kV, 2,210 MVA; re-measured 2026-11-22):
- 1.0 s: Pan de Azúcar-Punta Colorada 220 kV passes 120% and opens.
- 2.0 s: Maitencillo-Pan de Azúcar 110 kV passes 120% and opens; the corridor separates into a centro-sur island (115 substations, 7,872 MW of load) and a north island (73 substations, 3,223 MW).
- The pre-fault flow across the corridor was 2,209 MW N→S, over the 1,600 MW limit of the defence scheme, so both islands collapse by voltage (a rule, `engine.md` 6).
- 18.2 million people without power, 11,096 of 11,096 MW (100%), 2 stages. The real 25F: about 19 M people (98.5%).
- Cambios lists the user's cut apart from these consequences (lines opened by overload and islands that went dark, with their second).

The same cut at `feb2025-0300` loses only 631 MW. Solar is off at night and coal and hydro run (EVIDENCE: carrier table above). ASSUMPTION: the corridor carries less and the system has more inertia, which explains the smaller loss. Do not present these numbers as a forecast.

![Right panel](images/mapa3-panel.jpg)

## 7. Limits and assumptions

- DC flow: no voltage, no reactive power.
- Base case is secure for N-0 only. 10 to 21 lines start at their limit (N-1 is not imposed).
- Overload threshold 120%, 1.0 s per stage: ASSUMPTION, illustrative timing.
- Reserve 4% of online synchronous MW, damping 1.5 %/Hz, blackout under 47.5 Hz: ASSUMPTION except the 47.5 Hz limit (CEN 25F report).
- No ride-through trips, no batteries, no HVDC, no operator actions, no restoration.
- Storage in PyPSA-CL named `<TYPE>_<node>_<h>h` is expansion candidates, not real batteries.
- A cut takes out a whole merged corridor, not one circuit.
- Not calibrated against the 25F numbers beyond the one comparison above.
- The reduction (188 buses) contradicts the 10 to 14 aggregated nodes in `docs/stack.md`. The engine follows the reduction.

## 8. Data flow and files

```
data/scripts/*  ->  data/processed/{operating_points,baseline_opf}.json
backend cascade engine  ->  cache_builder  ->  web/public/cache/   (committed)
web/src/cascade/*  reads cache/*.json and draws it
```

| File | Role |
|---|---|
| `web/public/cache/index.json` | Points and assumptions |
| `web/public/cache/network-<year>.json` | The 188 substations and 273 lines |
| `web/public/cache/<point>/buses.json` | Generation, demand, people per substation |
| `web/public/cache/<point>/baseline.json` and `<line id>.json` | One timeline per cut: events, frames, frequency curves, summary |
| `web/public/cache/<point>/health.json` | Pre-fault health index and N-1 money at risk (`health.md` "Cost"); cut timelines also carry `health` and the cost in `summary` |
| `web/src/cascade/Scenarios.tsx` | Escenarios in the rail: Desastres (cuts, with the real event's date and figure) and Condiciones de operación (operating conditions without a cut) |
| `web/src/cascade/search.ts` | Cold start search: every line and substation by name, and the match for a typed text |
| `web/src/cascade/CascadeApp.tsx` | Design v5 shell: state (selection, cut, point), animation loop (clock, layers, HTML overlays), keyboard, rail, panel, controls |
| `web/src/cascade/powerAll.ts` | Pure rules of **Prender todo**: when it is enabled (`canPowerAll`) and what it resets (`powerAll`) |
| `web/src/cascade/clicks.ts` | Pure click interpreter: the first click selects, a second click on the selected line or substation switches it off, a fast double click does nothing, on both basemaps |
| `web/src/cascade/outage.ts` | Pure helpers: whether a line or substation is off (`isSwitchedOff`, with or without a session), batches of 3 for `POST /{sid}/cut` |
| `web/src/cascade/SelectionCard.tsx` | Card of the selected line or substation, at the top of the panel |
| `web/src/cascade/simulation.ts` | Reads a timeline at second t: dark set, impact, island frequency, event markers and their map places |
| `web/src/cascade/layers.ts` | deck.gl layers and colour constants |
| `web/src/cascade/NetworkPanel.tsx`, `SimulationPanel.tsx` | Tabs Red and Simulación |
| `web/src/cascade/Timeline.tsx`, `MapLegend.tsx`, `MapOverlays.tsx` | Timeline card, map legend, event pins and callout |
| `web/src/cascade/api.ts`, `types.ts` | Loads the cache files (`/cache/...`, memoised) and the types of their JSON |
| `web/src/cascade/gridsApi.ts` | Client of the backend grid documents (catalogue, compose, simulate, dependency, outage cost; `docs/grids.md`) |
| `web/src/cascade/GridSources.tsx` | "Redes disponibles" in the rail: choose which stored network is on the map |
| `web/src/cascade/NetworkState.tsx` | Tab "Cambios": every change made to the grid, restorable one by one or all at once |
| `web/src/cascade/edits.ts` | Pure list of the user's edits (lines cut, substations out) and the rule for when the cache can answer |
| `web/src/cascade/heat.ts` | Heat map layers (population, dependency, criticality) |
| `web/src/cascade/networkSummary.ts` | Figures of the Red tab by voltage band, from the network on the map |
| `web/src/cascade/url.ts` | Reads and writes the deep link (`point`, `cut`, `sesion`, `pais`) |
| `web/src/cascade/ui.tsx` | Shared pieces: info tooltip and icons |
| `web/src/cascade/cities.ts` | Reference city list (metadata, not drawn) |
| `web/src/cascade/Legend.tsx` | "Ayuda" and "Fuentes y supuestos" views |
| `web/src/cascade/text.ts` | Spanish narration of events, place names, number and clock formats |
| `web/src/cascade/cascade.css` | Styles of the shell (Design v5 tokens) |
| `web/src/incidents/` | **Incidentes** rail item: catalog, launch in a session at the incident's hour, consequence card, agentic response, prevention, cycles and their cascade on the map (section 4.2) |
| `web/src/assistant/` | **Asistente** rail item: chat with the in-app assistant, its steps live, the map following its session (`docs/assistant.md` section 2c) |
| `web/src/map/shapes.ts` | Outline of the rectangular bars |
| `web/src/map/country.ts`, `countryBounds.ts` | Network catalog, `countryOf`, `?pais=`; camera frame, limits and land from the data (section 4.1) |
| `web/src/map/regional.ts` | Loads one country's drawn layer (`loadCountryGrid`) and its outline (`loadOutline`); layers `regional-*` |
| `web/src/map/upload.ts`, `uploadStore.ts`, `iso3.ts` | Upload validation, browser storage, ISO3 list |
| `web/src/cascade/NetworkPicker.tsx`, `UploadNetwork.tsx` | Network selector in the panel header; upload form |

The frontend only reads files. All physics is in `backend/src/cascadasen/domain/cascade/`.

Regenerate data, in order (needs `scipy`: `cd backend && uv sync --group data`, and run the scripts with `uv run`; `build_operating_points.py` downloads PyPSA-CL files into git-ignored `data/raw/pypsa_cl/`):

```bash
python data/scripts/build_node_index.py
python data/scripts/build_operating_points.py
python data/scripts/build_baseline_opf.py
cd backend && PYTHONPATH=src python -m cascadasen.application.cache_builder
```

## 9. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Red note "Faltan datos de la simulación en esta versión de la app." | The cache is missing; the browser console names the file. Run `cascadasen-cache`. |
| Offline outline instead of Mapbox | No `VITE_MAPBOX_TOKEN` in `web/.env.local`, or the token is invalid. Restart `npm run dev` after editing. |
| Blank map, console shows `deck: ... Assertion failed` | A `ColumnLayer` with custom `vertices` needs `diskResolution` equal to the vertex count (4). Fixed in `layers.ts`. |
| Click does nothing | You clicked off a line (the cursor turns into a pointer over anything clickable). Zoom in. Lines are thin. The first click only selects: the card opens at the top of the panel. To cut, click the selected line again (slowly: a fast double click does nothing) or use "Sacar de servicio" in its card. A substation works the same way ("Apagar subestación"). After a cut, the event pin can cover a short cut line so it cannot be clicked; reconnect it with **Volver a conectar** in the impact card. |
| Double click does not cut | By design: a double click never switches anything off (a double click on empty map zooms on Mapbox with a mouse). Click once to select, then click again. |
| Never commit | `web/public/cache/theater/` (generated, git-ignored), `.env*`, `data/raw` |

## 10. Operation mode: the strategic theatre on this map (backend contract)

The strategic theatre (`docs/strategy.md`) now runs on the same network and engine as this map. A run lasts 24-36 cycles of 5 minutes. In each cycle, digital degradation (telemetry loss, delayed or unreliable data, communications loss, false alarms), an adaptive adversary acting by area, unplanned external events, and the defenders' decisions and field crews play out. A physical event runs the same cascade engine as a line cut here. This section is the contract for the frontend. **Backend only for now:** the API, the snapshots and the offline cache are done; the visual layer of mapa 3 is not part of this PR and is left to the frontend work. The only part the web uses today is the Incidentes view (section 4.2), which plays a cycle's `transient` on the map. A user flow that fits it: pick hour, scenario, defence policy and adversary; play 5-minute cycles drawing `grid`, areas and crews; replay `transient` in seconds; click a line or substation to inject an event (`POST /events`, applied next cycle); end with the report, the after-action and a replay with another policy (`/replay` + `GET /snapshots`).

**Sources.**
- Live: the API under `/api/v1/sim/*` (`docs/stack.md` 7.1). Every run without `seed` is a different random run.
- Offline fallback: `web/public/cache/theater/`, written by `uv run cascadasen-sim-fixtures` (git-ignored; the cut cache in `web/public/cache/<point>/` is committed).

**Areas.** The 13 operating areas `A01`-`A13` are groups of the 188 buses by latitude band. Corridors (`A06-A07`) are the `R###` lines that cross between two areas. Defence functions are `edac:norte_grande` and `edac:centro_sur`. The adversary acts only on areas, zones or defence functions, never on a single bus or line (`cyber.md` 8.7).

**Types**, reusing `web/src/cascade/types.ts`:

```ts
interface TheaterNetwork extends Network {          // GET /sim/network?point=  |  cache/theater/network-<point>.json
  point: string; points: string[];
  nodes: (NetNode & { area: string })[];
  lines: (NetLine & { corridor: string | null })[];
  buses: Record<string, BusState>;
  areas: { id: string; name: string; zone: string; lat: number; lon: number; population: number; buses: string[]; anchor_bus: string }[];
  corridors: { id: string; a: string; b: string; lines: string[] }[];
  defenses: Record<string, string[]>;                 // edac:<zone> -> areas
}
interface TheaterSnapshot {                         // one per 5-min cycle: POST /sim/runs/{id}/step  |  cache run file .snapshots[]
  cycle: number; t_min: number;
  events: { effect: string; type: string; target: string; area: string | null; source: "scenario" | "user" | "adversary" | "external"; cause: string; status: string }[];
  grid: Frame & { buses: Record<string, number> };  // quasi-steady state at the end of the cycle; draw it with layers.ts
  transient: Timeline | null;                       // the cascade (seconds) when a physical event happened this cycle
  areas: Record<string, { observability: number; posture: "normal" | "manual" | "segmented"; effects: { id: string; type: string; source: string }[] }>;
  crews: { id: string; base: string; position: string; bus: string; lon: number; lat: number; task: string | null; target: string | null; target_bus: string | null; arrival: number | null; status: "free" | "busy" }[];
  observed: unknown; estimated: unknown; decisions: unknown[]; executed: unknown[]; metrics: unknown;   // panels
  llm: { status: "chosen" | "unavailable" | "idle" | "replayed"; model: string | null; chosen?: string[]; explanation?: string } | null;  // C2 with an LLM, when the run has llm_commander
}
```

**How the two clocks fit.** The operation mode belongs in the main map (`/`). The player moves cycle by cycle (5 min) and draws `grid` with the existing layers: `buildCascadeLayers({ network, buses, frame: snapshot.grid, time, selected, mode })`, with the same `mode` (`"2d" | "3d"`, `?vista=2d`) as the cut viewer. In 2D the demand is drawn as discs, in 3D as columns; `snapshot.grid.buses` gives the served MW per bus to scale them. When `transient` is not null, the viewer can replay that cascade inside the cycle with the same code as a cut (`frames`, `events`, `frequency_hz`). An area overlay can colour areas by `observability` and `posture`. Crews are drawn at `lon`/`lat` and move toward `target_bus` until `arrival`.

**Other endpoints the frontend needs:** `GET /sim/runs/{id}/snapshots?start=` (snapshots already computed, e.g. after `/replay`, which runs all its cycles at once) and `GET /sim/catalog` → `llm: {available, model}` (whether the server has an LLM commander configured).

**Offline index** (`cache/theater/index.json`): `{points, runs: [{file, point, template, policy, seed, adversary}], notice}`. Each run file holds `{run, recipe, snapshots, report, after_action, trace_head}`.

Never shown: the adversary's learned weights or any ranking of areas or elements. Every run carries the notice "Escenario hipotético: se modela el efecto, no el ataque."

## 11. Session mode: a shared, editable copy of the network
Without a session, mapa 3 reads only the static cache (`web/public/cache/`) and makes no `/api` request, so it works with no backend. With a session it reads the sessions API (`docs/sessions-api.md`) through `/api`, which the Vite dev server proxies to the backend (`VITE_API_TARGET`, default `http://localhost:8000`; docker compose sets `http://backend:8000`). In production CloudFront and the ALB already route `/api/*` to the backend (`docs/infrastructure.md`), but until the sessions bucket and task role are applied the deployed backend keeps sessions in memory (`CASCADASEN_SESSION_STORE` defaults to `memory`), so they are lost on every restart or deploy. Test session mode on the local stack until then.

**Sources.**
| Mode | Network and buses | Timeline | Point |
|---|---|---|---|
| No session (`/`) | `cache/network-<year>.json`, `cache/<point>/buses.json` | `cache/<point>/<cut>.json` | Time pill |
| Session (joined by an incident run; `?sesion=` is not read on load) | `GET /api/v1/sessions/{sid}/network` | `GET /api/v1/sessions/{sid}/state` (the shared sandbox cut) | Pinned by the session; the conditions in the rail tree are disabled |

**Entering and sharing.** Status: shared sessions are hidden from the web (#101, commit `778e545f`). The rail has no session item (`web/src/cascade/CascadeApp.tsx`, `<nav className="rail">`: Mapa, Escenarios, Validación, Fuentes y supuestos, Asistente, Incidentes, Ayuda), no code calls `setView("session")`, so the **Sesión compartida** card (`SessionBar` without `compact`) and its **Crear sesión** / **Unirse** buttons cannot be reached, and `useSession` starts with no session (`useState<string | null>(null)`): `?sesion=` in the address is **not read** when the page loads. A session is created through the API (`POST /api/v1/sessions`, `docs/sessions-api.md`) by an API client, the MCP server or the assistant (the assistant tools open a session on first need, `mcp/toolbox.py`); the web does not join the assistant's session either (`useAssistant.ts`). The one web path that still creates and joins a session is **Incidentes**: `useIncident.launch` calls `createSession` and `join`, and from then on the session code described below is live (the panel-head strip with the session label, the revision, the live mode and **Salir de la sesión**, the **Datos** tab, cuts through `POST /{sid}/cut`). The strip has no share link, because a `?sesion=` link would open the plain map. **Salir de la sesión** calls `leave()` and returns to the plain map (the cache, with the tabs Simulación, Red and Cambios); the session itself stays on the server until it expires. A long session label ends in an ellipsis, so the strip never overflows the panel. While a session is joined the id is written to the address as `?sesion=<sid>` (`useSession.ts`, `_setUrl`), but reloading the page with it starts without a session. The live mode is **en vivo** (SSE stream `GET /{sid}/events`) or **sondeo** (no `EventSource`, or the stream gave up: `GET /{sid}` every 2 s with `If-None-Match`). A session that no longer exists (404) is forgotten and the map falls back to the cache. When the `dataset_revision` changes the page refetches the session, the network and the state; run activity (`run_created`, `run_updated`) refetches only the session document. When refetches overlap (`web/src/session/loader.ts`), the network and state of the newest full refetch are always applied, and a session document only when no newer document read started, so a run event during a dataset refresh no longer drops the new network.

**Cuts in a session.** A second click on a selected line, or **Sacar de servicio** in its selection card, calls `POST /{sid}/cut` with that line: it opens for everyone in the session and stays open until someone repairs it. **Volver a conectar** in the selection card of an open line repairs that line; **Volver a conectar**/**Volver a conectar todas** in the impact card repairs every open line (`{all: true}`). **Simulación** starts with the card **Líneas abiertas en la sesión · N**, which lists the open lines with **Reparar** (`POST /{sid}/repair {lines}`) and **Reparar todo** (`{all: true}`) and shows the notice the API returns; the impact card names every open line after `Corte:`. The session pins the operating point and owns the cut, so the Escenarios tree in the rail is locked (`ScenarioTree` with `locked`): the folders only fold and unfold, and every entry except the active one is disabled with the tooltip "En una sesión el punto está fijo; corta y repara líneas en el mapa y en Simulación.". The active entry is "Apagón 25F" when `R239` is the only open line, otherwise the condition of the session's point. The URL keeps `?sesion=` and drops `point` and `cut`. **Apagar subestación** in a session (or a second click on the selected substation) sends that substation's lines that are still closed through `POST /{sid}/cut`, in calls of at most 3 lines (`CutIn` limit), each with `If-Match` set to the `dataset_revision` the previous call returned; the session then holds them as ordinary open lines (there is no `sub-` id in a session). The card reads "apagada" and **Volver a encender** while all its lines are open, and that button repairs all its lines, including any the user had cut on its own. **Prender todo** (section 4, item 9) asks "¿Prender toda la red? Repara todas las líneas abiertas para todos los participantes de la sesión." and, on OK, repairs every open line (`POST /{sid}/repair {all: true}`) and clears the selection and the timeline. Session dataset edits stay; **Restablecer** in Datos is what drops them.

**Tabs in a session:** **Red**, **Simulación** and **Datos**. The two placeholder tabs (Qué lo habría evitado, Validación) are hidden in a session so the three tabs fit the 440 px panel; without a session the tabs are main's four and there is no Datos tab.

**Tab Datos** (only in a session): the session's copy of the network. Until the network arrives it shows "Cargando la sesión…".
- Header: the session's base case without cuts (`baseline`: highest line loading, overloaded lines, MW shed), each redispatch (`balance`) and every warning. **Restablecer** (`POST /{sid}/reset`) drops all session edits after a confirmation.
- Sub-tabs **Barras**, **Líneas**, **Generadores** and **Cargas y datacenters**: add forms, a list with an origin tag (`base` or `sesión`) and the label **supuesto (sesión)** on every session or overridden value, and per element a form that sends only the changed fields (`PATCH`), **Fuera de servicio** / **Poner en servicio** (`in_service`) and **Borrar** for session elements (base elements cannot be deleted).
- **Elegir en el mapa** turns the next map click into the latitude and longitude of the form. For a load or datacenter, **Conectar a la subestación ≥220 kV más cercana** picks the nearest in-service bus of 220 kV or more (`web/src/session/geo.ts`, great-circle distance). That is the only geometry the browser computes; balance and cascades come from the API.
- **One write at a time.** While a change and the reload after it are pending, every Datos control is disabled ("Guardando el cambio y recargando la sesión…") and `useSession.edit` refuses a second write; each write sends the `dataset_revision` of the newest network applied, so two quick edits from the same tab no longer get a 412 against themselves.
- **Field checks.** Each form checks its fields before sending, with the API's bounds (`api/session_schemas.py`): required fields, numbers with a decimal comma or dot, MW more than 0 and up to 3.000 for a load or generator, line capacity up to 5.000 MW, latitude between -56 and -17 and longitude between -76 and -66, bus ids like B010. The message sits under its field (`web/src/session/forms.ts`). A validation error that still comes back from the API names the fields in Spanish.
- **Numbers.** MW keep one decimal below 100 ("2,5 MW"); the highest line loading has one decimal ("100,2 %"), and when the engine holds lines at their limit (100,0 %) the count reads "líneas en su capacidad máxima". The filters have a visible label and a placeholder at 6.5:1. The header explains the tag "supuesto (sesión)": a value that this session added or changed, not from the public data.
- Edits send `If-Match` with the `dataset_revision` on screen. If another client changed the dataset first (412), the page reloads and asks you to retry. Run activity by other clients does not cause a 412. Every session request that gets the busy 409 (`sessions-api.md` section 7) waits `Retry-After` and is retried up to 2 times. Once the write is accepted the edit counts as done (the form closes) even if the reload after it still fails; the page then shows that reload error and keeps the network on screen until the next revision event reloads it. A busy 409 on the first load keeps the session and retries the load every 3 s; network errors and 5xx fall back to the base case. Overlay warnings in **Datos** use a neutral note, because red is reserved for faults.

**Files.** `web/src/session/sessionApi.ts` (typed calls for every session route, `ApiError`, `sessionIdFrom`, `subscribe`), `useSession.ts` (state and refetch), `loader.ts` (which refetch result is applied), `SessionBar.tsx` (the view card and the compact strip), `SessionCut.tsx` (open lines in Simulación), `DataPanel.tsx`, `forms.ts` (field rules and number formats of Datos), `geo.ts`, and `session.css` (session styles under `.shell`: radius 0, cascade.css tokens, `.tag` for labels because `.shell .badge` is the event marker). `CascadeApp.tsx` wires them into the shell.
## 12. Glossary

- **SEN**: Sistema Eléctrico Nacional, Chile's main grid.
- **CEN**: Coordinador Eléctrico Nacional, the system operator.
- **EDAC**: Esquema de Desconexión Automática de Carga, automatic load shedding by frequency steps.
- **N-1**: the grid survives the loss of any single element. Not imposed here.
- **Island**: part of the grid that is electrically separated and has its own frequency.
- **Inertia**: energy in rotating machines (MW·s). More inertia, slower frequency change.
- **Primary reserve**: capacity that synchronous machines add automatically when frequency falls.
- **Ride-through**: ability of a plant to stay connected during a short disturbance. Not modelled.
- **25F**: the 25 February 2025 national blackout.
