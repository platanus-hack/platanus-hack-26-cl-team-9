# Design

Last updated: 2026-11-21. Visual direction for the Sub50 web app, collected from the design sessions of 2026-11-21. Read after `stack.md` section 5, which this file overrides on look and layout. Nothing here is implemented in `web/` yet: the current app (`web/README.md`) predates these designs.

## 1. Where the designs live

All mockups are in the team's Paper file "Platanus Hack": https://app.paper.design/file/01M7WH997FX8E0HA2WZ2CZ9ES0

| Page | What it holds | Status |
|---|---|---|
| Draft Design | The backend test map (`/map`) rebuilt as one desktop artboard, all of Chile plus the full panel | Reference only; the team wants to improve it a lot |
| Design v1 (Claude) | First pass: 6 screens x 3 variations (A, B, C), glowing "night lights" style | Rejected as "too AI" |
| Design v2 (Claude) | Same 6 screens x 3 variations in the Electricity Maps style, plus tower-level views Z1-Z3 (Nueva Pan de Azucar, a selected tower, a tower fault) | Current reference for screens. Frame 6C was blocked by a Paper sync error; check it exists |
| Design v1 / v2 (Gemini) | Gemini's variations; v2 has 5 "control center" options on charcoal grays | Alternatives, not chosen |
| Design v3 | The 5 zoom levels from all of Chile down to S/E Calama (section 4), in the variant A interface | Reference for the zoom levels |
| Design v4 | Felipe's review of v3 applied to 3 frames: V1 Red, V2 Simulación en curso, V3 Después del corte (section 3.1) | Current reference for the map and the simulation |
| Logo Ideas | 20 black and white logo options, 1000 x 1000 (section 6) | Option 01 (Subscript) chosen, in `project-logo.png` |
| Battle Page | Ideas for a "Batalla" tab that shows the attacker vs defender agent game | In progress; see the open decision in `plan.md` section 9 |
| Vacía (borrar) | Empty page created by mistake | Delete by hand (Paper's API cannot delete pages) |

The six screens in Design v1 and v2: (1) resting state, (2) element selected, (3) cascade in progress, (4) after the cut, (5) "¿Qué lo habría evitado?", (6) validation against the 25F case.

## 2. Style

Copy the visual language of Electricity Maps (app.electricitymaps.com) closely. The team rejected two other directions: a glowing "night lights" map with glass cards, and an editorial or cartographic restyle of the same layout.

- **Layout (variant A):** dark nav rail, one rounded floating panel on the left with a header, underline tabs and soft inner cards, map on the right. A time pill at the top center, square icon buttons on the right, a legend card at the bottom right and a timeline card with play, scrub and a small frequency curve.
- **Map:** flat neutral gray land, neighbouring countries drawn, thin borders, solid fills. The map is the focus; the sidebar stays quiet.
- **Background:** dark neutral gray, not pure black.
- **Text:** sentence case. No all-caps eyebrow labels. No filler or hint text that does not carry information.
- **Numbers:** tabular figures, and an info icon next to each number that opens its source (`stack.md` section 5.3).
- **UI language:** Spanish. Do not show "SEN" as a product name; the product is Sub50.
- **Type (Valentina's review, 2026-11-21):** Geist Sans only. No Inter and no mono face: numbers, timers and code use Geist with tabular figures (`font-variant-numeric: tabular-nums`). Applied to every artboard of the Battle Page; the other pages still mix Inter and Geist Mono.
- **Corners (Valentina's review, 2026-11-21):** 0 to 2px on containers, tables, buttons and tags; no pills or large radii, because critical-infrastructure tools should read as precise. Applied to the Battle Page at 2px. The file's `--radius-*` tokens (3 to 16px) and the layout bullet above ("rounded floating panel", "time pill") are not updated yet; the team must decide whether the rule covers the whole app.
- **Docked modules (Valentina's review, 2026-11-21):** panels over the map dock to the nav rail and the artboard edges instead of floating, share one 20px inner margin, and separate sections with 1px dividers, like a mission console. No tilted or offset elements: cards in a hand sit on one horizontal line. Applied to B1 (HUD and event log) and B5 (cards); B11 has the same floating HUD and log and is not changed yet.
- **Event panel as an incident sheet (same review):** the last-move panel reads as a contingency report with three labeled rows: element out of service, effect on the system, critical variables. Applied to B1.
- **Two sides, two colors (same review):** the battle uses only red `#EF6A5A` (attacker, failure, lost load) and blue `#5AB0FF` (defender, recovery) plus neutrals. No green deltas, no light-blue labels, no tinted badges. Context and cost figures (MWh, US$) stay white. Code blocks are one neutral color with no syntax highlighting. Move notation marks ("!!", "!", "?!") are bold white, not colored. Applied to B4, B7 and B10.
- **Wording (same review):** people are never "a favor del atacante". The battle simulates agents and the consequences of their moves, so figures describe effects, for example "personas en riesgo de quedar sin luz" (`cyber.md` section 8).

## 3. Color

| Element | Color | Rule |
|---|---|---|
| 500 kV lines | Magenta | Voltage hues follow the OpenInfraMap convention. Lightness falls with voltage (OKLCH L about 0.80, 0.76, 0.71, 0.67, 0.63 from 500 kV down to MT), so 500 kV is the brightest |
| 220 kV lines | Orange | |
| 110 kV lines | Blue | |
| 66 kV lines | Green | |
| Medium voltage (MT) | Gray | |
| Plants | Solid disc in the technology color with a dark glyph | One color per technology, the same on the map and in the panels. Discs never read as lines. Thermal is a grayish brown, not purple |
| Substations | Dark box with a light border | Must not blend with roads |
| Faults and overloads | Red | Reserved: nothing else is red. Out-of-service lines are dashed gray |
| Cities and population | Cream | Reserved |

The colorimetry was checked in OKLCH on 2026-11-21. Problems it fixed: 66 kV outshone 500 kV, plant colors collided with voltage colors (hydro with 110 kV, wind with 66 kV, thermal with 500 kV), buildings read as muddy brown, and substations had the same gray as roads.

### 3.1 Design v4 rules (review of 2026-11-21)

- **One meaning per color at a time.** In the Red tab, line color is voltage. In the Simulación tab, line color is load (% of capacity) on a gray-to-red ramp: under 50 % gray, 50-75 % light gray, 75-100 % pale red, over 100 % red and thicker. Out of service is dashed gray; no voltage is near-black. Stroke width keeps showing voltage in both tabs, so the load ramp never reuses the voltage hues (in v2, orange meant 220 kV in one tab and about 75 % load in the other).
- **Legends use line samples**, not a segmented bar, so a categorical legend does not read as a percentage bar. Legend labels match the panel labels (154-345, 100-110, 44-69).
- **Events are numbered once and shown in three places**: the panel's "Historial de eventos", markers on the timeline track, and pins on the map. The current event is red and has an expanded tooltip on the map; past events keep a pin, and the first one keeps a short label. Events that happen within a few tenths of a second share one marker ("1·2").
- **The timeline** shows the frequency of each island as a small curve above the track, the played part of the track in white, and the event markers on it.
- **Assumptions live in context**: a "N supuestos en esta simulación" row in the panel and the info icon next to each number. The nav rail no longer has "Referencia / Metodología / Supuestos"; it has one "Fuentes y supuestos" item, and under "Escenarios" it lists the active and recent scenarios.
- The simulation map images were made by recoloring the v3 N1 SVG with a throwaway script (not in the repo). The event times and numbers are invented for the mockup, as in section 5.

## 4. Zoom levels

At country zoom the map shows lines only: no city glow and no "lit" effects. Icons appear as the user zooms in, in order of the real size and importance of what they represent. Warmth for "has power" appears only at the closest zoom, and very subtly. The legend shows only what is visible at the current level. A dashed box marks the area of the next level, and a breadcrumb in the panel follows the path.

| Level | Example view | What is added |
|---|---|---|
| 1 | Chile (cropped at Chiloe, where the SEN ends) | Lines of 220 kV and above only |
| 2 | Region of Antofagasta | All lines, substations of 220 kV and above, plants of 100 MW and above |
| 3 | Province of El Loa | All substations, plants of 9 MW and above |
| 4 | Calama | Real footprint of each plant and substation, the MT network; residential areas stay neutral gray |
| 5 | S/E Calama | Towers, poles, gantries, transformers, buildings with a faint warm tone |

Icons drawn so far: lattice tower, pole, gantry, transformer (two circles in the colors of its two voltages), substation, breaker, solar plant, thermal plant.

## 5. Data behind the mockups

The mockups use real positions, but some of their data is not in the repo pipeline (`datasets.md` section 1):

- **Basemap (streets, water, buildings, boundaries, names):** Mapbox Streets v8 (`datasets.md` source [40]). Mapbox has no grid data.
- **Grid at levels 1-4:** IDE Energia data already in `data/processed/`.
- **Towers, poles and transformers near Calama and Nueva Pan de Azucar:** OpenStreetMap (`datasets.md` source [41]). Not in the pipeline. OSM has little MT network loaded around Calama.
- **Invented for the mockups:** the internal bay layout of the substation yard, the tower numbering (counted from the substation, not the official number), and the fault sequence and population numbers in the cascade frames, which come from the model, not from a recorded event.

The map images were generated by throwaway scripts (`genzoom.py`, `genlevels.py`) that are not in the repo. To use these views in the app, the data has to enter the pipeline first.

## 6. Logo

The name refers to grid frequency: Chile's grid runs at 50 Hz, and when frequency drops below 50 the lights go out. Logo Ideas holds 20 black and white options on 1000 x 1000 artboards (the size Platanus asks for):

- Options 1-10 play on "below 50" (subscript wordmark, a bar over 50, a stepped drop, a flatlining wave) and on the grid and the game (open breaker, two islands, spreading dots, cut edge, contested node).
- Options 11-20 say more about the product, mostly with "sub50" as a wordmark and some with a short Spanish tagline. Taglines are unreadable at the 200 px the README uses, so a version without text is needed for small sizes.
- Option 01 (Subscript) is being refined: the "0" of the subscript 50 is a power button drawn as a Geist-width oval, so it reads "sub₅₀".

The team chose option 01. `project-logo.png` holds it: black "sub" with a subscript "5" and a power-button "0" on white, 1000 x 1000 PNG, 40 KB (Platanus asks for under 500 KB, `plan.md` section 8). The current file is a larger crop: the wordmark fills more of the square so it reads at the README's 200 px.

The favicon, `web/public/favicon.svg`, is the small-size mark: only the subscript "5" and the power-button "0", black on a white 32 x 32 tile with 2px corners, because "sub" is unreadable at 16 px. The "5" is Geist at weight 800 converted to a path (a favicon cannot load web fonts), and the power button reuses the stroke paths of the Paper "Logo" page, with the same spacing as the logo. A small-size version of the full wordmark (for the README or social cards) is still open.

## 7. Open items

- Pick the variant to build (A is the working reference).
- Port the Design v2 and v3 look into `web/`. The current app uses a full-screen map with a floating right panel and generation columns (`web/README.md`).
- Decide whether the demo uses the Mapbox basemap (needs internet and a token) or the offline map (`stack.md` section 1).
