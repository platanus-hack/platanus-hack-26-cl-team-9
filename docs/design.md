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
| Design v3 | The 5 zoom levels from all of Chile down to S/E Calama (section 4), in the variant A interface | Current reference for the map |
| Logo Ideas | 20 black and white logo options, 1000 x 1000 (section 6) | No pick yet |
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

`project-logo.png` is still the template logo. Export the chosen option as a 1000 x 1000 PNG under 500 KB (`plan.md` section 8).

## 7. Open items

- Pick the variant to build (A is the working reference) and the logo.
- Port the Design v2 and v3 look into `web/`. The current app uses a full-screen map with a floating right panel and generation columns (`web/README.md`).
- Decide whether the demo uses the Mapbox basemap (needs internet and a token) or the offline map (`stack.md` section 1).
