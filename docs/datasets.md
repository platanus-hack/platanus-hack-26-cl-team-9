# Datasets

Last updated: 2026-11-21. Status labels: **verified** (opened or downloaded and checked in this project), **not verified** (listed in earlier research, not checked), **missing** (no source found yet).

## 1. Summary

| Dataset | Needed for | Source | Status |
|---|---|---|---|
| Power plants (location, MW, technology) | Generator columns, node generation | IDE Energia MapServer layers 1-6 | **In pipeline** (1,193 operating SEN plants, 37,963 MW) |
| Transmission lines (geometry, kV, length, circuits, name) | Line layer, network edges | IDE Energia layer 10 | **In pipeline** (1,128 lines; end points inferred, see section 0) |
| Substations | Nodes | IDE Energia layer 8 + CEN Infotecnica | **In pipeline** (1,217 located; joined to CEN by `ID_SUBEST` = Infotecnica `id`) |
| Official line sections with end points | Topology | CEN Infotecnica `/v1/tramos/` | **In pipeline** (1,944 sections; 1,895 with both ends resolved) |
| Energy storage (batteries) | "What would have prevented it" | IDE Energia layer 9 + PyPSA-CL StorageUnits | **In pipeline** (91 + 244 records) |
| Line reactance and thermal limit | Power flow, overload rule | PyPSA-CL `Topology.xlsx` (Ministerio de Energia) | **Found**: 323 lines with r, x (pu and ohm) and s_nom (MVA); attached to 151 line edges |
| Scenario generation and demand per node | Scenarios | PyPSA-CL `Loads.xlsx`, `Topology.xlsx`, `Profiles.xlsx`, `Costs.xlsx`; CEN operation base Oct 2026 (zip) | **Built** for 4 operating points: modelled demand per bus and simulated merit-order dispatch (`data/processed/operating_points.json`), plus a secure DC-OPF base case (`baseline_opf.json`). Simulated, not measured. The CEN zip is not used |
| 25F figures for validation | Tests | CEN and university reports | **Verified** (see `plan.md` section 5) |
| Comuna and region outlines | Base map | INE Censo 2024 FeatureServer layer 11 | **In pipeline** (345 comunas, simplified to 1.2 MB) |
| Population per commune | "People without power" | INE Censo 2024 layers 11 and 2 | **In pipeline** (18,480,372 people; urban census zones for allocation) |
| Plant -> node assignment | Network build | PyPSA-CL generator bus, then substation name, then nearest | **Done** (1,073 by declared model bus) |
| Comuna -> substation (service areas) | People affected per node | Own rule on INE census zones | **Done**, flagged as assumption |
| Public cyber incidents on the SEN | Cyber scenarios, case V10 (`cyber.md`) | pv magazine articles citing CEN daily reports [34][35] | **Read** (secondary source) |
| Critical loads (hospitals, water, Metro) with location | Question Q4 in `cyber.md` | None found | **Missing** |
| Other countries' grids (Argentina, Bolivia, Brazil, Peru), context layer | Drawn under Chile's, never simulated (`regional.md`) | EPE WebMap (Brazil), Osinergmin GISEM (Peru), OpenStreetMap (Bolivia), Secretaría de Energía (Argentina) | **Built** for Brazil, Peru, Bolivia and (from OSM) Argentina; Argentina's official source was unreachable on 2026-11-21 |
| Brazil flow network: declared line ends, r, x, shunt, ampacity, substation coordinates | Ready for a DC flow, not wired to the engine (`regional.md` section 6, `network-format.md`) | ONS Dados Abertos [42], [43] | **Built** 2026-11-21 (`BRA/network.json`). Units of r, x and shunt inferred from magnitudes (ONS does not state them) |
| Basemap (streets, water, buildings, place names) | Zoom-level designs (`design.md` section 4), `?mapa=2` in `web/` | Mapbox [40] | **Used** by `web/` `?mapa=2` and the Paper mockups; needs a token and internet |
| Towers, poles, transformers, MT lines | Closest zoom levels (`design.md` section 4) | OpenStreetMap [41] | **Mockups only** (Calama, Nueva Pan de Azucar); not in the pipeline |

The pipeline that downloads, unifies and validates all of this lives in `backend/` (see `backend/README.md`). Section 0 summarises what it does. Sections 2-5 are the original research notes; where they conflict with section 0, section 0 is current.

## 0. Unified pipeline (2026-11-21)

`cascadasen-build` downloads every source into `data/raw/<source>/` (git-ignored cache), unifies them into one graph and writes `data/processed/`. `cascadasen-api` serves it. The test map lives at `/map`, and a self-contained copy is written to `data/processed/atlas_sen.html`.

How the sources are joined:
1. **Substations**: IDE Energia supplies the coordinates. IDE `ID_SUBEST` equals the Infotecnica substation `id` (1,163 of 1,170 have the same name). Infotecnica busbars add voltage levels. CEN-only substations take coordinates from the PyPSA-CL bus with the same name when one exists.
2. **Lines**: the IDE layer has no from/to fields. Each line end goes to a substation by distance plus a match with the line name ("A - B 220KV"). Taps (TAP OFF) split the host line. 94% of these edges have names that agree with both ends.
3. **Official topology**: each Infotecnica section declares its two ends as a bay (`Paño: PA S/E X B1/PA005L0089SE001L0089`, where the trailing code contains the substation code), a tap or a structure point. 1,124 sections confirm an IDE edge. 735 have no public geometry and are added as dashed straight segments.
4. **Electrical parameters**: PyPSA-CL lines attach to edges joining the same sites at the same voltage. Values describe the whole corridor (`corridor_edges` says how many parallel lines share it). Example: Nueva Maitencillo - Nueva Pan de Azucar 500 kV: 216 km, 2,210 MVA, X = 12.7 ohm.
5. **Population**: each urban census zone goes to its nearest delivery substation (zonal, or national at 220 kV or less, excluding plants, taps and switching stations). The rural remainder of each comuna is split among the delivery substations inside it. This is an assumption, not the real feeder map.

Validation (18 checks, all passing on the current build; `GET /api/v1/validation`):
- Coverage: 16/16 regions, SEN from -18.4 to -43.1 degrees latitude, 99.3% of substations sit inside the comuna polygon their IDE code names.
- Connectivity: 11/11 corridors of the 500 kV backbone, a continuous path from Chapiquina to Quellon, 99.3% of SEN MW and 98.2% of the population in the main grid (the rest is Aysen and Magallanes, separate systems).
- 25F: removing Nueva Maitencillo - Nueva Pan de Azucar 500 kV alone does not split the grid. The north separates only when both 220 kV circuits around Punta Colorada and the coastal 110 kV path (Maitencillo - Algarrobo - Incahuasi - Las Companias) also open. This is a test in `backend/tests/validation/`.

Built on top of `data/processed/` by standalone scripts in `data/scripts/` (merged in #10, not part of `cascadasen-build`):
- `build_operating_points.py` -> `operating_points.json`: demand per electrical bus from PyPSA-CL `Loads.xlsx` (259 loads, 252 mapped to model buses) and merit-order dispatch from PyPSA-CL generators (2,056 with bus, cost and inertia), solar and wind profiles and fuel prices. Synchronous units stay online until 31,000 MWs of inertia. Four points: Feb 2025 15:00 (25F reference) and 03:00, Nov 2026 13:00 and 20:00. PyPSA-CL has one representative day per month, so these are modelled, not measured. Downloads the four files into the git-ignored `data/raw/pypsa_cl/`. Needs openpyxl (a main dependency). Skips the SharePoint request when the four files are already there, and writes each download to `.part` first.
- `build_baseline_opf.py` -> `baseline_opf.json`: DC optimal power flow per point so no branch exceeds s_nom (NTSyCS art. 5-27), with the same inertia floor. All four points solve without load shedding. N-1 is not enforced. Needs numpy and scipy. Run after the previous script.
- `build_node_index.py` -> `node_index.json` (1.4 MB): one record per substation or tap for the web map popup (ficha, lines, plants, storage, served comunas, PyPSA-CL model, demand and dispatch). PyPSA-CL storage named `<TYPE>_<node>_<h>h` is shown as model candidates, not real batteries.

Data quirks found while unifying:
- The IDE storage layer has no geometry. The pipeline rebuilds it from `COORD_ESTE/COORD_NORT/HUSO` (sub-10 m error checked against the substation layer).
- Two Magallanes substations (Cabo Negro, Vientos Patagonicos) carry `SIST_ELECT = SEN`. The pipeline relabels regions 11 and 12 as SEA and SEM.
- Infotecnica tap names repeat across regions ("TAP RIO HUASCO" exists in Atacama and Maule). The pipeline keys taps by name and voltage, and rejects straight segments longer than plausible for their voltage.
- Several names use an en dash ("CUMBRE – NUEVA CARDONES"). It must be replaced before folding to ASCII.
- The census FeatureServer ignores `maxAllowableOffset` for GeoJSON (32 MB of comuna polygons). The adapter simplifies the polygons itself.
- Three public "concesiones de distribucion" FeatureServers that appear in searches are not Chilean (Dominican Republic and Ecuador). No public GIS layer of Chilean distribution concessions was found.

## 2. Power plants (downloaded)

### 2.1 Source

Ministerio de Energia, IDE Energia, Visor IDE Energia MapServer (ArcGIS REST). Plant geometry comes from the Ministry, sourced per record from CEN, SEC, CNE, SEIA and others (`FUENTE_BAS`).

Base URL: `https://ide-energia.minenergia.cl/server/rest/services/IDE_Energia/Visor_IDE_Energ%C3%ADa/MapServer`

| Layer id | Name | Geometry |
|---|---|---|
| 1 | Bioenergia | point |
| 2 | Geotermicas | point |
| 3 | Eolicas | point |
| 4 | Solares | point |
| 5 | Termoelectricas | point |
| 6 | Hidroelectricas | point |
| 8 | Subestaciones | point |
| 9 | Almacenamiento de Energia | point |
| 10 | Linea de Transmision | polyline |
| 12-16 | Fuel storage, marine terminals, regasification, gas pipeline, oil pipeline | not needed |

Query: `GET {base}/{layer}/query?where=1=1&outFields=*&outSR=4326&f=geojson&resultOffset=N&resultRecordCount=2000&orderByFields=OBJECTID`. Maximum 2,000 records per page; the plant layers fit in one page each.

Plant layer fields: `OBJECTID, ID_GE_*, NOMBRE, PROPIEDAD, TIPO, MEDIO_GENE, COMBUSTIBL, POTENCIAMW, UNIDADES, RCA, SIST_ELECT, ESTADO, F_OPERACIO, COORD_ESTE, COORD_NORT, HUSO, DATUM, REGION, PROVINCIA, COMUNA, FUENTE_BAS, FECH_CREA, FECH_ACT`.

Line layer fields: `ID_LIN_TRANS, SUBTIPO (voltage code), NOMBRE, CIRCUITO, TIPO, F_OPERACIO, LONG_KM, TRAMO, PROPIEDAD, TENSION_KV, RCA, SIST_ELECT, ESTADO, REGION, PROVINCIA, COMUNA, FUENTE_BAS`. Voltage codes: 100 = 500-345 kV, 101 = 220 kV, 102 = 154 kV, 103 = 110 kV, 104 = 66 kV, 105 = under 66 kV. The layer description says the line data was provided by the CEN and includes medium systems (Los Lagos, Aysen, Magallanes).

### 2.2 What was downloaded

| Layer | Records downloaded | Operating SEN plants after filtering | MW |
|---|---|---|---|
| Solar | 746 | 745 | 12,194 |
| Thermal | 207 | 170 (136 are diesel) | 11,134 |
| Hydro | 190 | 179 | 7,485 |
| Wind | 71 | 66 | 6,401 |
| Bioenergy | 32 | 32 | 666 |
| Geothermal | 1 | 1 | 84 |
| **Total** | 1,247 | **1,193** | **37,964** |

Largest plants: Atacama (thermal, 716 MW), Guacolda (703 MW), Ralco (hydro, 685 MW), Pehuenche (543 MW), Kelar (517 MW), Angamos (506 MW), Cochrane (490 MW), Pangue (466 MW), Colbun (461 MW), El Toro (437 MW). All plants have coordinates and MW above 0. Regions present in the SEN set: Tarapaca to Los Lagos plus Aysen (1 plant); no Magallanes.

### 2.3 Unified file and where it lives

A previous session wrote these under `~/Desktop/Hackathon/cascadasen/datos/` on Alonso's machine (outside this repo):
- `raw/centrales_{bioenergia,eolicas,geotermicas,hidroelectricas,solares,termoelectricas}.geojson`
- `centrales_sen.geojson`: 1,193 operating SEN plants with fields `nombre, tecnologia, mw, combustible, propietario, region_cod, region, comuna_cod, fuente`.

To get them in the repo, copy those files into `data/` or regenerate with Appendix A and B (the scripts were not committed, see the appendices). Raw files are about 800 KB; the unified file is about 430 KB, small enough to commit. Licence and terms of use of the IDE Energia data were not checked.

### 2.4 Data quirks (read before filtering)

1. `ESTADO` uses two labels for the same thing: `OPERATIVA` (solar, geothermal) and `EN OPERACION` (the other four layers). A filter on one label drops about 40% of plants. Accept both.
2. `POTENCIAMW` is installed capacity (nameplate), not generation. Use it for column size and for the maximum a plant can produce. Real dispatch for a scenario must come from another source (the CEN operation base or the 25F reports).
3. The layers include plants outside the national grid: `SIST_ELECT` also has `SEA` (Aysen), `SEM` (Magallanes), `LOS LAGOS`, `ISLA DE PASCUA` (the thermal layer has a point at longitude -109.4), `PARTICULAR` and others. Filter `SIST_ELECT == "SEN"`.
4. `REGION`, `PROVINCIA` and `COMUNA` are INE codes (strings), not names. Region codes: 01 Tarapaca, 02 Antofagasta, 03 Atacama, 04 Coquimbo, 05 Valparaiso, 06 O'Higgins, 07 Maule, 08 Biobio, 09 La Araucania, 10 Los Lagos, 11 Aysen, 12 Magallanes, 13 Metropolitana, 14 Los Rios, 15 Arica y Parinacota, 16 Nuble. Commune names are in the layer metadata (`?f=json`, field domains) if needed.
5. Two plants appear in more than one layer with identical name and coordinates (El Traro, Nuevo Reino). They are not SEN plants in the unified set, but deduplicate by (name, rounded lon/lat) anyway.
6. Unified output has 1,193 plants, which is too many to draw as individual columns. Aggregate per node (see `stack.md` section 5.2).

## 3. Companion data from the CEN Infotecnica API (verified, not downloaded)

`https://api-infotecnica.coordinador.cl/v1/centrales/` returns, per plant: `id, propietario_nombre, comuna_nombre, region_nombre, central_tipo_nombre, codigo, nemotecnico, nombre, coordinado_nombre`. It does **not** return coordinates or power. Use it to cross-reference plant names, owners and communes only. The transmission-segments endpoint under the same API returns names, owners and end points but no electrical parameters (reactance, thermal limit).

## 4. Missing data and how to handle it

### 4.1 Line reactance and thermal limits (main data risk)
Neither IDE Energia nor Infotecnica has them. The full network model is a PowerFactory `.pfd` (about 96 MB, proprietary) inside the CEN zip. Options, in order:
1. Check whether the two Excel files in the zip (https://www.coordinador.cl/wp-content/uploads/2026/10/2610-BD-OP-COORD-DMAP.zip) contain impedances and limits. Not checked.
2. Use typical reactance per km by voltage level times line length, calibrated so the 25F corridor splits about 1,800 MW over the 500 kV pair and 314 MW over the 220 kV link, with capacity 2,317 MW [4]. Mark every such value `is_assumption: true`. This makes the flow split a calibration, not a validation.
3. Plan A (optional): a contact with a PowerFactory licence exports cases to pandapower JSON. Needs written permission from the organisers because the rules require all team members present and forbid remote participation. If there is no verified conversion by 10:00 on Saturday, drop it.

### 4.2 Scenario generation and demand per node
CEN operation base October 2026 has 10 scenarios plus one with distributed generation. Only "ERNC CC Maxima" (12:18) and "Laboral Diurno" (16:34) have lots of sun. Use those two plus "Domingo Diurno-PMGD". Inertia per scenario is 31.0 to 42.4 GVAs (earlier research, not re-checked). Fallback if the spreadsheets are unusable: demand per node proportional to population, generation per plant = installed MW times a capacity factor by technology and hour (assumption).

### 4.3 Population and cities
INE Census 2024 by region/commune (https://censo2024.ine.gob.cl/resultados/). The mapping region -> electrical zone -> node is an assumption and must be declared. If a whole island blacks out count all its population; if it survives by shedding load, estimate affected people as the shed fraction of consumption and show "estimated".

### 4.4 Other
- Chile outline: continental only (drop Easter Island and Antarctic territory). Simplify with mapshaper. Not downloaded.
- Economic loss of the 25F: US$ 984 million and 81,430 MWh not served, ISCI study for Enel Foundation ("Estimación de Impactos de Blackouts en Chile", R. Moreno) [44]. The cascade cost uses it for two parameters (`cascade.yaml` `cost`): 7.34 h of black start and a total-blackout premium of 1.375 over the CNE failure cost [19] (docs/engine.md "Cost").
- Line capacity for corridors other than the 25F one: the CEN transmission-restrictions study may have it; current version not verified.

## 5. Plant -> node assignment (task)

The reduced network has 188 buses (`plan.md` section 9, decision 4). Every plant in `centrales_sen.geojson` must be assigned to a node by the nearest substation or by zone polygon, and node generation per scenario is built from the assigned plants. Document the rule. This step has not been done.

## 6. Provenance rule

Every number that reaches the UI carries a `source` (document + page/table, or API/layer) or `is_assumption: true`. A test must fail otherwise. Repo scripts download data; do not redistribute CEN model files (terms of use not checked).

## 7. Sources

| # | Document | URL | Status |
|---|---|---|---|
| 1 | Platanus Hack 26 rules | https://hack.platan.us/26-cl/bases | Verified |
| 3 | CEN, 25F failure analysis, executive summary | https://www.coordinador.cl/wp-content/uploads/2025/03/2025-03-19-RESUMEN-EJECUTIVO.pdf | Verified |
| 4 | U. de Chile, USM, USACH, systemic analysis of 25F, final report | https://www.coordinador.cl/wp-content/uploads/2025/08/InformeCEN_FINAL.pdf | Verified (175 pages) |
| 5 | CEN, Defence Plan study 2025 | https://www.coordinador.cl/wp-content/uploads/2025/10/Estudio-PDC-2025_Informe-Final.pdf | Verified (Table 4-11) |
| 6 | CEN, analysis and update of the north defence scheme (PDCE-ZN) | https://www.coordinador.cl/wp-content/uploads/2025/10/R-1171-25-CEN-Analisis-y-actualizacion-de-PDCE.pdf | Verified by earlier research |
| 9 | CEN, SEN modelling (PowerFactory bases) | https://www.coordinador.cl/modelacion-sen/ | Verified |
| 10 | CEN operation base Oct 2026 (zip: .pfd, 2 xlsx, 1 pdf) | https://www.coordinador.cl/wp-content/uploads/2026/10/2610-BD-OP-COORD-DMAP.zip | Opens; spreadsheet content not checked |
| 12 | CEN Infotecnica API | https://api-infotecnica.coordinador.cl/v1/centrales/ | Verified (no coordinates, no electrical parameters) |
| 13 | IDE Energia MapServer | see section 2.1 | Verified |
| 14 | CEN, EDAC study 2026 (automatic load shedding) | https://www.coordinador.cl/wp-content/uploads/2026/07/Estudio-EDAC-2026-Informe-Final.pdf | Verified (3,000 MW loss case) |
| 16 | CEN, Annex E of the 2026 ancillary services report (xlsx, defences) | https://www.coordinador.cl/wp-content/uploads/2025/12/2025.12.23-Anexo-E.-Control-de-Contingencias.xlsx | Verified by earlier research |
| 18 | CEN, ancillary services proposal 2026 | https://www.coordinador.cl/wp-content/uploads/2026/06/Informe-Propuesta-SSCC-2026_20260327.pdf | Verified by earlier research |
| 19 | CNE failure cost, 8.79 US$/kWh for the SEN | https://www.cne.cl/wp-content/uploads/2026/03/Res.-Ext.-N112-comunica-CFCD-y-CFLD.pdf | Verified |
| 29 | INE Census 2024 | https://censo2024.ine.gob.cl/resultados/ | Page verified |
| 30 | INE Censo 2024 FeatureServer (behind visualizador.ine.gob.cl) | https://services5.arcgis.com/hUyD8u3TeZLKPe4T/arcgis/rest/services/Censo2024_v2/FeatureServer | Verified, in pipeline (layer 11 comunas, layer 2 census zones) |
| 31 | CEN Infotecnica: substations, busbars, lines, sections, plants | https://api-infotecnica.coordinador.cl/v1/tramos/ (also `/subestaciones/`, `/barras/`, `/lineas/`, `/centrales/`) | Verified, in pipeline |
| 32 | PyPSA-CL model inputs, Ministerio de Energia (public SharePoint folder; licence not stated) | https://minenergia-my.sharepoint.com/:f:/g/personal/mparedes_minenergia_cl/IgCWD1vzVNdFSZGLq9yAvae7AWiPl3JViAfaI602hsQZTQ0?e=SH5uDd | Verified: `Topology.xlsx` in pipeline; `Loads.xlsx`, `Profiles.xlsx`, `Costs.xlsx` used by `data/scripts/build_operating_points.py` |
| 33 | Mapa de Vulnerabilidad Energetica (IDE Energia): comunas with households without electricity | https://ide-energia.minenergia.cl/server/rest/services/MAPA_VULNERABILIDAD/Mapa_de_Vulnerabilidad_Energetica/MapServer | Verified, not used |
| 34 | pv magazine, "Chilean solar plant offline for two months following cyberattack" (29 Oct 2026; cites the CEN daily report of 27 Oct 2026) | https://www.pv-magazine.com/2026/10/29/chilean-solar-plant-offline-for-two-months-following-cyberattack/ | Read in this project (secondary source; the CEN reports themselves were not opened) |
| 35 | pv magazine, "Chilean PV plant hit by cyberattack remains disconnected" (17 Nov 2026; cites the CEN daily report of 14 Nov 2026 and T13) | https://www.pv-magazine.com/2026/11/17/chilean-pv-plant-hit-by-cyberattack-remains-disconnected/ | Read in this project (secondary source) |
| 36 | Ley 21.663, Framework Cybersecurity Law (BCN) | https://www.bcn.cl/leychile/navegar?idNorma=1202434 | Found; legal text not read. Notification times taken from [35] |
| 37 | CNE, public consultation on the draft cybersecurity and information-security technical standard for the electricity sector (28 Aug 2026) | https://www.cne.cl/es/prensa/prensa-2026/08-agosto-2026/cne-inicia-consulta-publica-de-proyecto-de-norma-tecnica-de-ciberseguridad-y-seguridad-de-la-informacion-para-el-sector-electrico/print/ | Found via search; status of the final standard unknown |
| 38 | Idaho National Laboratory, Consequence-driven Cyber-informed Engineering (CCE) | https://www.inl.gov/cce/ | Found via search; not read in full |
| 39 | MITRE ATT&CK, 2016 Ukraine Electric Power Attack (campaign C0025) | https://attack.mitre.org/campaigns/C0025/ | Found via search. The 2015 and 2016 Ukraine figures in `cyber.md` come from secondary sources and are not verified |
| 40 | Mapbox (Streets v8 vector tiles, Standard style) | https://www.mapbox.com/ | Used: `web/` `?mapa=2` and design mockups. Requires a public token (`web/.env.local`, git-ignored) |
| 41 | OpenStreetMap power data (towers, poles, transformers, lines) | https://www.openstreetmap.org/ | Used in design mockups only (2026-11-21); ODbL licence requires attribution if shipped |
| 42 | ONS Dados Abertos, `linha-transmissao` (CC BY, updated daily): lines from 230 kV with bus numbers, r, x, shunt, ampacity | https://dados.ons.org.br/dataset/linha-transmissao (file `https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/linha_transmissao/LINHA_TRANSMISSAO.csv`) | Verified, downloaded 2026-11-21, in pipeline (`ons_brasil.py`). Dictionary states no unit for r, x, shunt: percent on 100 MVA and Mvar inferred (`regional.md` section 6) |
| 43 | ONS Dados Abertos, `subestacao` (CC BY): busbars from 69 kV with substation code and coordinates | https://dados.ons.org.br/dataset/subestacao (file `https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/subestacao/SUBESTACAO.csv`) | Verified, downloaded 2026-11-21, in pipeline |
| 44 | Revista Electricidad, "Estudio estima las pérdidas económicas generadas por el blackout del 25 de febrero": ISCI for Enel Foundation, US$ 984 million and 81,430 MWh not served for the 25F, by sector with interdependencies; cited in `pitch_idea.md` [1] | https://www.revistaei.cl/estudio-estima-las-perdidas-economicas-generadas-por-el-blackout-del-25-de-febrero/ | Press estimate, not verified: the study behind it was not opened and its method is unknown. Used only in `tests/validation/test_health_25f.py` and `docs/health.md` to order magnitudes, never shown in the UI |
| - | Article by CEN engineers on the 25F protection sequence | https://www.pacw.org/chilean-grid-blackout-of-february-2025 | Read by the evaluator |
| - | Andes (similar hackathon project, click-to-fail) | https://github.com/aleetreny/Encode | Verified |
| - | COSMIC (MATLAB dynamic cascade simulator) | https://github.com/ecotillasanchez/cosmic | Verified |
| - | pypsa-chile, PyPSA-CL | https://github.com/sanjaygrr/pypsa-chile , https://github.com/paredes-vergara/PyPSA-CL | Verified (economic dispatch, not security) |

Numbering follows the team's earlier research notes; gaps are sources not needed here.

## Appendix A: download script (`data/scripts/descargar_centrales.py`)
Not in the repo: the script was not committed, so the file named here does not exist.

```python
"""Download IDE Energia plant layers as GeoJSON into ../raw/."""
import json, os, urllib.parse, urllib.request

BASE = "https://ide-energia.minenergia.cl/server/rest/services/IDE_Energia/Visor_IDE_Energ%C3%ADa/MapServer"
CAPAS = {1: "bioenergia", 2: "geotermicas", 3: "eolicas", 4: "solares", 5: "termoelectricas", 6: "hidroelectricas"}
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "raw")
PAGINA = 2000
os.makedirs(OUT, exist_ok=True)

def pedir(capa, offset):
    q = urllib.parse.urlencode({"where": "1=1", "outFields": "*", "outSR": 4326, "f": "geojson",
                                "resultOffset": offset, "resultRecordCount": PAGINA, "orderByFields": "OBJECTID"})
    with urllib.request.urlopen(f"{BASE}/{capa}/query?{q}", timeout=60) as r:
        return json.load(r)

for capa, nombre in CAPAS.items():
    feats, offset = [], 0
    while True:
        data = pedir(capa, offset)
        if "error" in data:
            raise SystemExit(f"layer {capa}: {data['error']}")
        lote = data.get("features", [])
        feats += lote
        if len(lote) < PAGINA:
            break
        offset += PAGINA
    with open(os.path.join(OUT, f"centrales_{nombre}.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f, ensure_ascii=False)
    print(f"layer {capa} {nombre}: {len(feats)} records")
```

## Appendix B: unify script (`data/scripts/unificar_centrales.py`)
Not in the repo: the script was not committed, so the file named here does not exist.

```python
"""Unify plant layers into centrales_sen.geojson (operating SEN plants only)."""
import glob, json, os

AQUI = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(AQUI, "..", "raw")
REGIONES = {"01": "Tarapaca", "02": "Antofagasta", "03": "Atacama", "04": "Coquimbo", "05": "Valparaiso",
            "06": "O'Higgins", "07": "Maule", "08": "Biobio", "09": "La Araucania", "10": "Los Lagos",
            "11": "Aysen", "12": "Magallanes", "13": "Metropolitana", "14": "Los Rios",
            "15": "Arica y Parinacota", "16": "Nuble"}
TECNOLOGIAS = {"bioenergia": "bioenergia", "eolicas": "eolica", "geotermicas": "geotermica",
               "hidroelectricas": "hidro", "solares": "solar", "termoelectricas": "termica"}
OPERATIVO = {"OPERATIVA", "EN OPERACION"}  # two labels for the same state

salida, vistos = [], set()
for ruta in sorted(glob.glob(os.path.join(RAW, "centrales_*.geojson"))):
    capa = os.path.basename(ruta)[len("centrales_"):-len(".geojson")]
    for f in json.load(open(ruta, encoding="utf-8"))["features"]:
        p = f["properties"]
        if p["SIST_ELECT"] != "SEN" or p["ESTADO"] not in OPERATIVO or not p["POTENCIAMW"]:
            continue
        clave = (p["NOMBRE"], round(f["geometry"]["coordinates"][0], 4), round(f["geometry"]["coordinates"][1], 4))
        if clave in vistos:
            continue
        vistos.add(clave)
        salida.append({"type": "Feature", "geometry": f["geometry"], "properties": {
            "nombre": p["NOMBRE"], "tecnologia": TECNOLOGIAS[capa], "mw": round(p["POTENCIAMW"], 2),
            "combustible": p["COMBUSTIBL"], "propietario": p["PROPIEDAD"], "region_cod": p["REGION"],
            "region": REGIONES.get(p["REGION"], p["REGION"]), "comuna_cod": p["COMUNA"],
            "fuente": f"IDE Energia capa {capa} ({p['FUENTE_BAS']})"}})
with open(os.path.join(AQUI, "..", "centrales_sen.geojson"), "w", encoding="utf-8") as g:
    json.dump({"type": "FeatureCollection", "features": salida}, g, ensure_ascii=False)
print(len(salida), "plants,", round(sum(f["properties"]["mw"] for f in salida)), "MW")
```
