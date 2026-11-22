# Network format: how to build a network the app can read

Last updated: 2026-11-21. This document is for anyone who wants to add a country's transmission network, or upload one. You can follow it without reading the code. It fixes the data contract, the three readiness levels, how to fill missing data and how much error that adds, and what each level can honestly claim.

Worked files in the repo: Chile (`data/processed/grid_snapshot.json`, read by the engine), Brazil (`data/processed/latam/BRA/network.json`) and the drawn layers of Peru, Argentina and Bolivia (`data/processed/latam/<ISO3>/*.geojson`). Built by `cascadasen-build` (Chile) and `cascadasen-regional` (the others, `regional.md`).

## 1. Data contract

A network is one JSON document with a header and four lists: `buses`, `lines`, `dc_links` and `plants`. Brazil's `network.json` is the reference file for this contract. Chile's engine input carries the same information under other names (section 4.1).

### 1.1 Header

| Field | Type | Unit / values | Required | Meaning |
|---|---|---|---|---|
| `version` | int | `1` | yes | Contract version |
| `country` | string | ISO 3166-1 alpha-3 (`CHL`, `BRA`, `PER`) | yes | Every element repeats it |
| `built_at` | string | ISO 8601 date-time, UTC | yes | When the file was built |
| `as_of` | string | ISO date | yes | Lines entering service after this date are left out |
| `base_mva` | float | MVA, always `100` | yes | Per-unit base of every `_pu` field. The engine uses 100 MVA (`BASE_MVA`) |
| `frequency_hz` | int | `50` or `60` | yes | Nominal frequency. Chile 50, Brazil 60 |
| `level` | string | `L0`, `L1`, `L1+`, `L2` | yes | Readiness level (section 2) |
| `units` | object | text | yes | Unit of every numeric field, as written here |
| `sources` | list | see below | yes | Every dataset used |
| `warnings` | list of strings | Spanish text | yes | Everything dropped or guessed, with names and counts |

A `sources` item has `id`, `name`, `publisher`, `url`, `license`, `attribution`, `provides` (a list of the lists it feeds) and `fetched_at`.

### 1.2 Bus (one per substation)

| Field | Type | Unit | Required | Meaning |
|---|---|---|---|---|
| `id` | string | `<ISO3>-<code>` | yes | Unique and stable: take it from the source's own substation code, not from the position in the list |
| `name` | string | text | yes | Substation name as the source writes it |
| `lat`, `lon` | float | WGS84 decimal degrees | yes | Position; inside the country's bounding box |
| `kv` | float | kV | yes | Highest voltage of the lines that reach the bus |
| `kv_levels` | list of float | kV | yes | All voltages of those lines, highest first |
| `coord_source` | string | `ons`, `epe_exact`, `epe_fuzzy`, ... | L1+ | Where the position came from |
| `country`, `source`, `is_assumption` | | | yes | Provenance (section 1.6) |

Voltage levels inside one substation are merged into one bus, and transformers are folded away. This is Chile's reduction (`engine.md`): a transformer does not change where a cut isolates power, and the DC flow has no voltage.

### 1.3 Line (AC corridor; parallel circuits folded)

| Field | Type | Unit | Required | Meaning |
|---|---|---|---|---|
| `id` | string | `<ISO3>-L<n>` | yes | Unique |
| `a`, `b` | string | bus `id` | yes | The two ends, **declared by the source** at L1 and above; `a < b` |
| `kv` | float | kV | yes | Highest voltage of the folded circuits |
| `circuits` | int | count | yes | Circuits folded into this line |
| `length_km` | float | km | yes | Longest of the folded circuits |
| `x_pu` | float | pu on `base_mva` | L1+ | Series reactance; > 0, floor 5e-4 |
| `r_pu`, `b_pu` | float or null | pu on `base_mva` | optional | Resistance and shunt susceptance (the DC flow ignores them) |
| `x_ohm`, `r_ohm` | float | ohm | optional | The same values in ohm: `pu × kV² / base_mva` |
| `capacity_mw` | float | MW | L1+ | Thermal limit. The engine trips a line above 1.2 × this value |
| `capacity_a` | list of float or null | A per circuit | optional | Source ampacity, `null` where missing |
| `assumed_fields` | list of strings | field names | yes | Fields filled with a typical value (section 3) |
| `branches` | list of strings | source codes | yes | Source records folded into this line |
| `country`, `source`, `is_assumption` | | | yes | `is_assumption` is true when `assumed_fields` is not empty |

How parallel circuits fold, as in Chile:
- **Capacities add up**, and so do the susceptances.
- **Reactances combine in parallel**: `x = 1 / Σ(1/xᵢ)`, and the same for r.

Conversions:
- **Ampacity to MW:** `capacity_mw = √3 × kV × A / 1000`. This is MVA, used as MW because the DC flow has no reactive power, as Chile uses `s_nom_mva`.
- **Percent to pu:** a value given in percent on 100 MVA (the ANAREDE and PSS/E habit) is `pct / 100` pu.
- **Ohm to pu:** a value given in ohm is `ohm × base_mva / kV²`.

### 1.4 DC link (HVDC)

Same fields as a line, with `dc: true` and no `x_pu`, `r_pu` or `b_pu`. A linear DC power flow cannot represent an HVDC link: it carries a set power, not a power split by angle. So DC links are kept apart, for a future fixed-injection model. `capacity_mw` may be `null` when the source states no rating.

### 1.5 Plant group (generation per bus)

| Field | Type | Unit | Meaning |
|---|---|---|---|
| `id` | string | `<ISO3>-G<n>` | Unique |
| `bus` | string | bus `id` | Bus the plants were added to |
| `mw` | float | MW installed | Sum of the plants |
| `mw_by_tech` | object | MW | Per technology: `solar`, `eolica`, `hidro`, `termica`, `bioenergia`, `geotermica`, `nuclear`, `otra` |
| `tech` | string or null | | Technology with the most MW |
| `count` | int | | Plants added |
| `country`, `source`, `is_assumption` | | | Provenance |

### 1.6 Provenance rule

Every number that can reach the UI carries a `source` (the dataset and, where useful, the layer or column) or `is_assumption: true`. This is the rule of `datasets.md` section 6, and the YAML loader `check_provenance` in `domain/simulation/params.py` refuses a parameter without it. A value filled from section 3 is named in `assumed_fields` and in the `source` text (`"...; supuesto: capacity_mw"`).

## 2. Readiness levels

| Level | Has | Allows | Who is there today |
|---|---|---|---|
| **L0, drawing** | `lines`, `substations`, `plants` GeoJSON in the common schema v2 (`regional.md` section 2). Line ends were snapped by distance | Drawing the grid, km per kV, MW per technology | Peru, Argentina (OSM), Bolivia (OSM); Brazil's drawn layer |
| **L1, topology** | Line ends declared by the source (bus numbers or substation codes), one bus per substation | Graph cascade: which cut isolates which buses, critical corridors by structure. No MW | — |
| **L1+, topology and line parameters** | L1 plus real `x_pu` and `capacity_mw` for each line | DC flow once injections exist; line-loading ranking under assumed injections | **Brazil** (`BRA/network.json`) |
| **L2, flow** | L1+ plus, per bus: load, generation, synchronous MW and inertia, people; a secure base case (DC-OPF) | Everything the engine does: MW cut, frequency, people without power | **Chile** |

L2 is what `minimum-dataset.md` section 1.1 calls the engine inputs: 7 values per bus and 5 per line.

## 3. How to fill gaps

A filled value always goes into `assumed_fields` and carries `is_assumption: true`.

### 3.1 Measured error of the usual fillers (Brazil, 2026-11-21)

Brazil is the one country where the real ONS values sit next to the drawn layer, so the error a deduced network carries can be measured there. `deduction_error` in `domain/regional_network.py` gives each real AC circuit the value a country without data would use, and compares it with the ONS value. The relative error is `|deduced − real| / real`. Figures are in `manifest.json` under `countries.BRA.flow.deduction_error`.

**Reactance.** The filler is the midpoint of the typical ohm/km range for the nearest class (`X_PER_KM` in `domain/validation.py`) × the length. Circuits shorter than 5 km are left out.

| kV | Circuits | Median error | p90 error | Median bias |
|---|---|---|---|---|
| 230 | 958 | 17 % | 33 % | −12 % |
| 345 | 162 | 3 % | 38 % | +2 % |
| 440 | 63 | 5 % | 18 % | +5 % |
| 500 | 408 | 18 % | 72 % | +17 % |
| 525 | 87 | 5 % | 18 % | +4 % |
| 765 | 9 | 3 % | 4 % | −3 % |
| **all** | 1,687 | **15 %** | **39 %** | +1 % |

The 500 kV p90 is high, and the real x there is lower than typical, which fits series compensation of long 500 kV lines. That cause was not checked line by line.

**Capacity.** The filler is the typical rating of the nearest class (`typical_capacity_mva` in `domain/simulation/params/network.yaml`: 220 kV 400, 345 kV 900, 500 kV 1,700 MVA).

| kV | Circuits | Median error | p90 error | Median bias |
|---|---|---|---|---|
| 230 | 939 | 34 % | 73 % | +23 % |
| 345 | 169 | 16 % | 56 % | +5 % |
| 440 | 66 | 12 % | 16 % | +12 % |
| 500 | 364 | 32 % | 42 % | −32 % |
| 525 | 83 | 31 % | 49 % | −31 % |
| 765 | 6 | 59 % | 59 % | −59 % |
| **all** | 1,627 | **31 %** | **62 %** | −1 % |

Chile's typical ratings underrate Brazil's 500 kV lines by about a third. A country-specific median does better: Brazil uses the ONS median per kV for its 215 circuits without amperes (`typical_capacity_mw` in `network.json`: 230 kV 324, 345 kV 855, 440 kV 1,524, 500 kV 2,503, 525 kV 2,464, 765 kV 4,133 MW).

**Topology.** The filler snaps line ends to the nearest substation by distance, which is how the L0 layers are built. The test compares Brazil's drawn layer (EPE geometry, `regional_reduction.py`) with the ONS-declared corridors, on the 728 substations both layers share (snapped within 3 km):

| Measure | Value |
|---|---|
| Drawn corridors compared | 1,160 (122 more had an end with no ONS bus nearby) |
| Of them, real ONS corridors (precision) | 89 % |
| ONS corridors found by the drawn layer (recall) | 99 % |

About one corridor in nine that distance snapping creates does not exist as a direct line in the operator's data. Usually the drawn layer chained two lines through a substation the drawing source does not have.

Use these figures as the expected error for Peru, Argentina and Bolivia when they are deduced. They are a lower bound there: EPE draws a full official layer, while OSM is incomplete (`regional.md` section 3).

### 3.2 Fillers whose error was not measured

| Missing | Filler | Where the value lives | Quality |
|---|---|---|---|
| Generation per bus | Installed MW per technology × a plant factor per technology and hour | Plant MW from the L0 layer; factors not chosen yet | Low-medium; not measured |
| Load per bus | National demand split by population (WorldPop or GHS-POP, CC BY 4.0, `regional.md` section 4) | Not built | Low, the weakest input; not measured |
| Inertia | Typical H per technology | `inertia_h_s` in `domain/simulation/params/physics.yaml` (thermal 4 s, hydro 3 s; solar and wind 0) | Medium; not measured |
| Base case | DC-OPF on the filled injections | Chile only (`baseline_opf.json`) | Depends on the inputs |

In a DC flow, injections (generation minus load) and reactances fix the result. If load is split by population, the flows mostly reflect that split. Brazil's ONS hourly load (`curva-carga`) and hourly generation per plant (`geracao_usina_2_ho`) could measure this error in a second phase.

## 4. Worked examples

### 4.1 Chile, L2 (`grid_snapshot.json`)

- **Topology and parameters:** PyPSA-CL `Topology.xlsx` (Ministerio de Energía). It gives buses `name_<kV>` and branches with `bus0`, `bus1`, `x_pu` (100 MVA), `s_nom_mva` and `build_year`.
- **Geometry:** IDE Energía (Ministerio de Energía) for lines and substations, and CEN Infotecnica for the inventory.
- **Load:** PyPSA-CL `Loads.xlsx`.
- **Dispatch, synchronous MW and inertia:** DC-OPF (`baseline_opf.json`).
- **People:** INE Censo 2024.

The engine reads `model_buses` and `model_branches` and folds them per substation (`reduce_network` in `domain/cascade/network.py`): 188 buses and 273 lines. Field mapping to this contract:

| This contract | Chile |
|---|---|
| bus `id` | `model_buses[].name` without the `_<kV>` suffix |
| line `a`, `b` | `bus0`, `bus1` |
| `capacity_mw` | `s_nom_mva` |
| `as_of` | `build_year` |

### 4.2 Brazil, L1+ (`BRA/network.json`)

**Sources:**
- ONS `linha-transmissao`: every line from 230 kV, with its two bus numbers, r, x, shunt and ampacity.
- ONS `subestacao`: every busbar from 69 kV, with its substation code and coordinates.
- EPE WebMap: plants, plus a coordinate fallback by name.

**Steps** (`cascadasen-regional --countries BRA --ons`):

1. Keep the lines in service: 1,875 of 2,348 rows; none enter service after `as_of`.
2. Join each line end (`num_barra_de` and `num_barra_para`) to a busbar, then the busbar to its substation (`id_subestacao`). This gives one bus per substation. 853 of 855 substations have ONS coordinates. The other two (USIBA 230 kV, COL BOA SORTE 2 500 kV) are not in EPE either, so their 2 lines are dropped with a warning.
3. Drop and list in `warnings`:
   - 18 lines whose other end is not in the ONS registry: Uruguay (Rivera, Melo), Argentina (Rincón), Paraguay (Itaipu 50 Hz, Margem Direita) and Venezuela (Santa Elena). Interconnections are out of scope.
   - 5 *ramal* rows with no "to" end.
4. Convert units:
   - ONS does not state them. The magnitudes fit **percent on 100 MVA for r and x, and Mvar at nominal voltage for shunt** (the ANAREDE convention). Converted, the median x per circuit-km is 0.48 ohm/km at 230 kV and 0.28 ohm/km at 500 kV, textbook values. A validation test fails if the medians leave `X_PER_KM`.
   - The thermal limit is `val_capacoperlongacomlimit`: long duration, with the limiting factor (terminal equipment) included, so it is the real operating limit of the whole line.
5. Fill: 215 circuits with no ampacity use the ONS median MW per circuit for their kV (`assumed_fields: ["capacity_mw"]`). 11 circuits with no length use the straight distance between buses.
6. Fold parallel circuits: 1,842 circuits become 1,305 lines. The 12 HVDC records become 4 `dc_links`.
7. Attach EPE plants to the nearest bus within 40 km: 495 groups. 566 plants (13,107 MW) are farther away and are counted in the warnings.

**Checks:**
- Length: AC circuits add up to 174,428 km, 7.9 % below the MapYourGrid figure of 189,308 km (220 kV and up, not opened). With the 22,028 km of HVDC records it is 196,456 km, +3.8 %. The figure probably counts HVDC. The remaining gap comes from the 18 excluded cross-border lines and from how each source counts double circuits.
- Coordinates: ONS and EPE agree within a median of 50 m on the 582 substations with the same name; 9 are more than 10 km apart.

**Caveats:**
- The HVDC MW (`kV × A` per record) are unverified. Xingu gives 4,200 MW per bipole against 4,000 nominal, but Madeira gives 12,600 MW against 6,300. Itaipu's HVDC states no amperes.
- Brazil has no load, dispatch or people per bus yet, so it is L1+, not L2. It is not wired to the engine.

### 4.3 Peru, Argentina, Bolivia, L0

| Country | Today | Missing for L1 | Missing for L2 |
|---|---|---|---|
| Peru | Osinergmin GISEM geometry (`regional.md` section 3) | Declared line ends: COES technical sheets probably hold them with impedances (`coes.org.pe/Portal/Equipamiento/FichaTecnica`, not tested) | Load per bus and dispatch (COES pages with export, no API) |
| Argentina | OpenStreetMap (official Secretaría de Energía CSV unreachable) | CAMMESA PSS/E databases are agent-only; PyPSA-AR covers 500 kV only | CAMMESA demand endpoint per region (verified), no per-bus split |
| Bolivia | OpenStreetMap | CNDC publishes only single-line diagrams (PDF/DWG links were empty) | CNDC historical generation and demand, no per-bus split |

Until a source declares the line ends, these countries can only be deduced. Expect at least the errors of section 3.1.

## 5. Checklist to add a country

1. **Find the operator's data.** Electricity Maps' `DATA_SOURCES.md` (`regional.md` section 4) lists the operator of each country: AR CAMMESA, BO CNDC, BR ONS, CL Coordinador, CO XM, CR ICE, DO OC, EC CENACE, GT AMM, HN ENEE, MX CENACE, NI CNDC, PA CND, PE COES, SV UT, UY UTE. Look for, in order:
   - a line list with bus numbers or substation codes at both ends;
   - impedances and ratings;
   - a substation list with coordinates;
   - a geometry layer (official GIS, else OSM).
2. **Licence.** Write it down in `sources[].license`. Do not use GADM (non-commercial). When no licence is stated, cite the publisher.
3. **Units.** Read the data dictionary. When it states no units, check the magnitudes against typical ohm/km per voltage (`X_PER_KM`) and write down how you decided, as section 4.2 does for Brazil.
4. **Coordinates.** Prefer the operator's own coordinates. When joining by name, normalise first:
   - ASCII, upper case;
   - drop prefixes such as `SE` and `S/E`;
   - turn Roman numerals into Arabic ones.

   Then accept an exact match, or a similarity of 0.85 or more at the same voltage. List every substation left without coordinates in `warnings`, with its name and kV. Never drop one silently.
5. **Build** with an adapter in `infrastructure/sources/regional/` and the pure functions of `domain/regional_network.py`. Brazil's `ons_brasil.py` is the template.
6. **Minimum checks** (Brazil's are in `backend/tests/validation/test_ons_network.py`):
   - every element has `country`, `source` and `is_assumption`;
   - x > 0 and capacity > 0;
   - the median ohm/km per kV is typical;
   - one main connected component holds ≥ 95 % of buses;
   - total length is within ±15 % of the official figure;
   - the coordinate match is ≥ 98 %.
7. **Record** the source in `datasets.md` section 7 and in `regional.md`, and add a `CHANGELOG.md` entry.
8. **If the country stays at L0**, show it as a drawn layer only: gray, with no loading and no MW figures, as the regional layer does today (`regional.md` section 1).

## 6. Safety of uploaded files

This is the same requirement as issue #49 part C, which can validate uploads against this contract.

- **Read as data, never as code.** Parse with a JSON (or GeoJSON) parser only: no `eval`, no pickle, no YAML tags, no spreadsheet macros or formulas.
- **Names are text.** Render `name`, `source` and `warnings` escaped. Never interpret them as HTML, Markdown links or file paths.
- **Size limit.** Refuse files above a fixed size before parsing. Proposed: 10 MB, 5,000 buses, 10,000 lines (Brazil is 0.73 MB, 853 buses and 1,305 lines).
- **Range checks** before use:
  - `lat` within −90..90 and `lon` within −180..180, inside the declared country's box;
  - `kv` within 1..1500;
  - `x_pu` > 0 and `capacity_mw` > 0, all finite;
  - ids unique;
  - `a` and `b` name existing buses, with `a ≠ b`;
  - `country` from the ISO3 list.
- **Provenance is mandatory**: refuse an element without `source` or `is_assumption`.
- An uploaded network never overwrites a built-in one. It lives in the user's session.

## 7. What each level can honestly claim

| Level | Can say | Must not say |
|---|---|---|
| L0 | Where the grid runs, km per kV, installed MW per technology, which corridors look structurally critical (with the warning that the ends were snapped by distance, and about 1 in 9 corridors may not exist) | Anything about flows, MW cut or people without power |
| L1 | Which buses a cut isolates; critical corridors by structure | MW figures |
| L1+ | Line-loading patterns under stated, assumed injections, labelled as such | MW cut or people without power as if they were real |
| L2, real data | MW cut, frequency, people without power (Chile) | — (still a reduced DC model, `engine.md`) |
| L2, deduced data | The same figures, with an uncertainty label naming the deduced inputs and the error of section 3 | Precise-looking figures without the label |

Brazil-specific limits before it can reach L2:
- 60 Hz, while the frequency engine has Chile's constants: 50 Hz, the CEN EDAC tables and the 25F corridor.
- HVDC links need a fixed-injection model.
- The excluded interconnections are still listed "from memory, not verified" in `regional.md`.
