# Regional grids (context layer)

Last updated: 2026-11-21. The map draws the transmission networks of Argentina, Bolivia, Brazil and Peru under Chile's. They are **context only**: nothing here feeds the cascade engine (Brazil also has a flow network with real line parameters, section 6, still not wired to the engine), and `idea.md` section 4 still leaves international interconnections out of the simulation. Every element carries its source (`datasets.md` section 6). Status labels: **verified** (page or service opened in this project), **not verified** (seen in search or written from memory), **failed** (tried and could not reach).

## 1. What is built

| Piece | Where |
|---|---|
| Command | `cd backend && uv run cascadasen-regional --countries BRA,PER,ARG,BOL [--osm ARG] [--ons] [--refresh]` (`--ons` also builds Brazil's flow network, section 6) |
| Output | `data/processed/latam/<ISO3>/{lines,substations,plants}.geojson`, `data/processed/latam/manifest.json`, `data/processed/latam/outlines.geojson`; with `--ons`, `data/processed/latam/BRA/network.json` and `manifest.countries.BRA.flow` |
| Outlines | `data/scripts/build_latam_outlines.sh` (geoBoundaries ADM0) |
| Domain (pure) | `domain/regional.py`: schema, `parse_kv_levels`, `tech_from_text`, `normalise`, `feature_collections`, `manifest_entry`; port `RegionalGridSource` in `domain/ports.py` |
| Adapters | `infrastructure/sources/regional/`: `epe_brasil.py`, `osinergmin_peru.py`, `energia_argentina.py`, `osm_overpass.py`; wiring in `infrastructure/container.py` (`regional_use_case`) |
| Frontend | `web/src/map/regional.ts` (loader, layers `regional-*`, tooltip), legend block in `web/src/cascade/Legend.tsx`. Lines and substations reuse Chile's tokens from `web/src/cascade/layers.ts` (`VOLTAGE_TIERS`, `NODE_COLOR`) at full opacity; in the Simulación (load) view the lines are neutral gray `REGIONAL_NO_LOAD` (#767B80), outside the load ramp, because they carry no load |
| Reduction (pure) | `domain/regional_reduction.py` (`reduce_bundle`, `feature_collections`, `manifest_entry`) |
| Flow network (pure) | `domain/regional_network.py` (`build_flow_network`, `deduction_error`, `network_document`, `flow_manifest_entry`); adapter `infrastructure/sources/regional/ons_brasil.py`; port `FlowNetworkSource`; use case `BuildFlowNetwork` in `application/build_regional.py` |
| Tests | `backend/tests/unit/test_regional.py`, `backend/tests/unit/test_ons_brasil.py`, `backend/tests/validation/test_regional_data.py` and `test_ons_network.py` (skip without the data), `web/src/map/regional.test.ts` |

## 2. Common schema (v2, reduced)

The layer is reduced the same way as Chile's network (`cascade/network.py`, `engine.md`): one bus per substation, parallel lines folded into one, drawn as straight segments between two buses. The code is `domain/regional_reduction.py`; `normalise` in `domain/regional.py` runs first (filters and deduplication of the raw records).

Steps of `reduce_bundle`:
1. Substations closer than 3 km are one bus (the highest voltage gives its name and position); the voltage levels are merged.
2. Each end of a line goes to the nearest bus within 12 km; an end with no bus becomes a free point (OSM splits one line into many ways that share end points).
3. Free points with two lines are pass-through and the two lines are chained; free points with one line are dangling and that line is dropped; free points with three or more stay as `junction` buses.
4. Lines between the same two buses are folded: voltage is the maximum, circuits add up, length is the longest. Lines with both ends in one bus are dropped.
5. Connected pieces with fewer than 3 buses are dropped, then substations with no line.
6. Plants are added up per bus (nearest bus within 40 km, else dropped and counted in `warnings`): total MW, MW per technology, number of plants, dominant technology.

The four thresholds (3, 12, 40 km and 3 buses) are assumptions chosen by looking at the result, not calibrated; they are constants at the top of `regional_reduction.py`.

Result (2026-11-21), source records to reduced:

| Country | Lines | Substations | Plants |
|---|---|---|---|
| Brazil | 2,264 to 1,286 | 927 to 839 | 2,953 to 519 generation points |
| Peru | 575 to 246 | 269 to 198 | 246 to 102 |
| Bolivia | 244 to 58 | 71 to 54 | 31 to 15 |
| Argentina (OSM) | 3,056 to 390 | 308 to 300 | 208 to 81 |

Brazil and Argentina still have more elements than Chile's 188 buses and 273 lines because the countries are far larger. Plants far from any substation are lost (Brazil: 531 plants, 15,581 MW; Argentina: 70, 5,475 MW); the manifest and the command print it.

Files: `data/processed/latam/<ISO3>/{lines,substations,plants}.geojson` and `manifest.json` (counts reduced and raw, km per kV, MW per technology, sources with licence).

- **Lines** (`LineString`, two points): `id` `<ISO3>-R<n>`, `a`, `b` (bus ids), `kv`, `circuits`, `length_km`, `source`, `source_records` (first 20), `merged`.
- **Substations** (buses, `Point`): `id` `<ISO3>-B<n>`, `name`, `kv`, `kv_levels`, `kind` (`substation` or `junction`), `source`, `source_records`, `merged`.
- **Plants** (generation per bus, `Point` at the bus): `id` `<ISO3>-G<n>`, `bus`, `name`, `tech`, `mw`, `mw_by_tech`, `count`, `source`.
- Every feature has `country`, `source` and `is_assumption` (false: values come from the sources; the reduction thresholds are the only assumption, declared above).
- Lines and substations from 66 kV up; lines without voltage dropped; plants below 0.1 MW or not operating dropped.

No electrical parameters (r, x, thermal limit) exist in this layer, and the reduced lines are not a topology to simulate: the end points are resolved by distance, not declared by the source. Brazil's flow network (section 6) is the one exception, and measured this: about 11 % of the drawn corridors are not direct lines in the operator's data (`network-format.md` section 3.1).

## 3. Sources used

| Country | Source | Status | Notes |
|---|---|---|---|
| Brazil | EPE WebMap, `https://gisepeprd2.epe.gov.br/arcgis/rest/services/WMS_Webmap_EPE_Data/MapServer`: layer 23 lines (`Nome, Tensao, Extensao, Concession, Ano_Opera`), 22 substations, 14-21 plants by technology | **Verified**, built, see section 2 | `potencia` is in **kW** (Itaipú reads 14,000,000). 2,000 records per page. No licence stated |
| Brazil (flow) | ONS Dados Abertos `LINHA_TRANSMISSAO.csv` and `SUBESTACAO.csv` (CC BY), see section 6 | **Verified** 2026-11-21, built | `;`-separated UTF-8 with space-padded text. Units not stated by ONS (section 6) |
| Peru | Osinergmin GISEM, `https://gisem.osinergmin.gob.pe/serverosih/rest/services/Electricidad/MapaSEIN_Operacion/MapServer`: lines 28-32 by kV, substations 22-26, plants 6, 9, 12, 17-20 | **Verified**, built, see section 2 | `POT_INST` is in MW except four records typed in kW (Huanza, Callahuanca, Yanango, Carhuac); the adapter reads values above 3,000 as kW. SEIN only (isolated systems excluded). No licence stated |
| Bolivia | OpenStreetMap through Overpass (`power=line\|cable` with `voltage`, `power=substation`, `power=plant`) | **Verified**, built, see section 2 | No official GIS exists (CNDC publishes single-line diagrams only). ODbL: the legend shows "© OpenStreetMap contributors". OSM may include lines under construction (500 kV near Cochabamba) |
| Argentina | Secretaría de Energía CSV datasets (lines, transformer stations, plants), `http://datos.energia.gob.ar/dataset/...` (https refuses connections) | **Failed**: the server did not answer from this machine on 2026-11-21. **Built from OpenStreetMap instead** (`--osm ARG`): 390 lines after the reduction | The adapter `energia_argentina.py` detects columns by candidate names and reads GeoJSON, WKT or lat/lon; it is tested only on synthetic CSV. Run `cascadasen-regional --countries ARG` when the server answers and fix the candidate lists to the real header. The committed Argentina data is the OSM fallback; after the reduction it has 26,000 km against 37,293 km officially, so the duplicated circuits are gone but OSM is incomplete |
| Outlines | geoBoundaries gbOpen ADM0, simplified geometry | **Verified** | Licence varies by country (Argentina: CC BY 2.5). GADM is excluded because it forbids redistribution |

Quality check against official length (MapYourGrid index, CC BY 4.0, **not opened**, figures from earlier research): Argentina 37,293 km; Brazil 189,308 km (220 kV and up); Peru 28,711 km. After the reduction Brazil has 132,900 km (189,308 officially, but folding parallels and dropping lines with both ends in one bus removes length) and Peru 15,700 km (28,711 officially, SEIN only). The reduced lengths are the longest of the folded lines, not the sum, so they undercount. Brazil's 600 and 800 kV entries are the HVDC links.

## 4. Sources found and not used (for the next step)

### Region-wide

| Source | Status | Use |
|---|---|---|
| OpenStreetMap `power=*`, Geofabrik extracts `download.geofabrik.de/south-america.html`, Open Infrastructure Map | **Verified** | Uniform baseline for any country. No r, x or ampacity; line ends are not tagged. Worldwide 14.9% of line-km lacks voltage. Chile has about 70% of official length in OSM. The Caribbean is sparse |
| earth-osm (`github.com/pypsa-meets-earth/earth-osm`, MIT) | **Verified** | Ready tool for a uniform OSM pull of every country |
| Global Energy Monitor, Global Integrated Power Tracker | **Verified** page; licence inside the file **not verified** | Best uniform plant source (200+ countries, September 2026 release). No transmission data |
| WRI Global Power Plant Database | **Verified** | Frozen at v1.3.0 (June 2021), unmaintained. Do not use |
| GridFinder (Zenodo 3628142, CC BY 4.0) | **Verified** | 2020, no voltage per line, no substations. Only a gap filler |
| MapYourGrid transmission length index | **Verified** | Official line-km per country, to score OSM completeness |
| Global Transmission Database | **Verified** | Cross-border transfer capacity in MW, no geometry |
| PyPSA-Earth, PyPSA-AR (Argentina 500 kV, GeoSADI + CAMMESA PSS/E), PyPSA-Brazil (DLR, one node per state) | **Verified** | Methods for building a network and assigning r, x by voltage class when simulation is wanted |
| Electricity Maps contrib (AGPL-3.0) | **Verified** | `DATA_SOURCES.md` lists each country's operator API: AR CAMMESA, BO CNDC, BR ONS, CL Coordinador, CO XM, CR ICE, DO OC, EC CENACE, SV UT, GT AMM, HN ENEE, MX CENACE, NI CNDC, PA CND, PE COES, UY UTE, PR AEEPR |
| geoBoundaries (CC BY 4.0 for most), WorldPop R2025A (CC BY 4.0), GHS-POP R2023A (CC BY 4.0) | **Verified** | Admin units and population for any country. GADM v4.1 is non-commercial: avoid |
| OLADE sieLAC, CIER, EOR/SIEPAC, SINEA | **Verified** | Statistics and reports only, no grid download. IDB Hub de Energía returned HTTP 526 and ENERGYDATA.INFO 403 (**failed**) |

### Brazil (richest data in the region)

- ONS `linha-transmissao` and `subestacao`: **used**, section 6. `SUBESTACAO.csv` **does** have coordinates (`val_latitude`, `val_longitude`), contrary to what this section said before.
- ONS hourly generation per plant `dataset/geracao_usina_2_ho/GERACAO_USINA-2_{YYYY}_{MM}.csv`, hourly load `curva-carga`. **Verified.**
- ANEEL SIGEL (`sigel.aneel.gov.br/arcgis/rest/services`) and the SIGA registry refused connections (**failed**). IBGE APIs for municipal boundaries and census: **not verified**.

### Peru

- COES equipment and technical sheets (`coes.org.pe/Portal/Equipamiento/FichaTecnica`) probably hold line impedances (**not tested**). Demand by bus and executed dispatch are web pages with export, no documented API. No public network model.

### Argentina

- CAMMESA PSS/E static and dynamic databases are agent-only. Undocumented 5-minute demand endpoint `https://api.cammesa.com/demanda-svc/demanda/ObtieneDemandaYTemperaturaRegion?id_region=1002` (**verified** to answer). Other Secretaría de Energía datasets (towers, generation and transmission maps) **listed only**. INDEC census 2022 and IGN boundaries **not verified**.

### Colombia

- XM API, `POST https://servapibi.xm.com.co/hourly` (also `/daily`, `/lists`), no key, MIT repo `github.com/EquipoAnaliticaXM/API_XM`, wrapper `pydataxm`: hourly generation per plant and demand. **Verified.**
- UPME GIS runs ArcGIS Experience viewers (`sig.upme.gov.co`); no REST endpoint found (404). Next step: find the feature service behind the viewer. XM PARATEC (likely line parameters) is a JavaScript app that could not be read.

### Other South America

| Country | Finding |
|---|---|
| Ecuador | GIS only on request (ARCERNNR procedure); Atlas 2023 is PDF; `geoportal.cenace.gob.ar` does not resolve; SIMEM needs a digital-signature credential |
| Bolivia | CNDC (`cndc.bo`) has historical generation by source and demand; single-line diagrams linked but the PDF/DWG links were empty; GeoBolivia did not resolve |
| Paraguay | ANDE transmission master plan 2024-2033, annex II (PDF with capacities and diagrams; would need digitising); no GIS or hourly API |
| Uruguay | MIEM "Mapas Energéticos" ZIP, April 2017 (contents not inspected); ADME publishes SimSEE (energy models, not network) |
| Venezuela, Guyana, Suriname, French Guiana | No official open data; OSM only |

### Mexico, Central America, Caribbean

| Country | Finding | Ease |
|---|---|---|
| Dominican Republic | CNE ArcGIS account `https://services6.arcgis.com/ZxFYx8rM0YBg9sBr/arcgis/rest/services/`: `Líneas_de_Transmisión` (310 lines, kV, circuits, conductor), `Subestaciones`, `Centrales_Actuales_SENI_Nov2025` (no MW field), `Conceciones_de_Distribución` (the public distribution-concession layer found earlier is this one). **Verified** | Easy |
| Costa Rica | ICE ArcGIS account `https://services1.arcgis.com/cW2GfO4rBCLoFwgj/arcgis/rest/services/`: `LineasDeTransmision2023/FeatureServer/2` (Voltaje, Circuito), `Subestaciones2023/FeatureServer/3`, `Plantas_NGICE/FeatureServer/0` (ICE plants only). **Verified** layers | Easy |
| Mexico | CENACE web services without key: nodal prices `https://ws01.cenace.gob.mx:8082/SWPML/SIM/{SIN\|BCA\|BCS}/{MDA\|MTR}/{node}/{yyyy/mm/dd}/{yyyy/mm/dd}/JSON`, demand by load zone `.../SWCAEZC/SIM/SIN/MDA/{zone}/...`. **Verified.** No official line or substation GIS; NACEI MapServer (`geoappext.nrcan.gc.ca/arcgis/rest/services/NACEI/energy_infrastructure_of_north_america_en/MapServer`) has plants of 100 MW or more and cross-border crossings, no line geometry. **Verified** | Market data easy, geometry medium |
| Puerto Rico | EIA-860 generators with coordinates; HIFLD lines archived on DataLumos (DOI 10.3886/E240591V1) after the HIFLD shutdown of 26 Aug 2025; NREL PR100 (CC BY 4.0, hourly load). Only PR100 **verified** | Medium |
| Nicaragua | MEM Google My Maps (KML export); a third-party copy of ENATREL's 2011 line survey with no voltage field. **Verified** | Medium |
| Guatemala | CNEE atlas and transmission plan PET 2024-2054 as PDFs; no REST service; viewer PDF returned 503 | Medium |
| Panama, El Salvador, Honduras, Belize, Cuba, Haiti | PDFs, dashboards or nothing public; SIGET 403, ODS certificate error. OSM is the practical geometry source | Hard |
| SIEPAC / EOR | Regional PSS/E base held by EOR and not public; annual lists of the regional transmission network (`enteoperador.org/identificacion-de-la-red-de-transmision-regional/`) and a real-time flow map. **Verified** | n/a |

Interconnections (from memory, **not verified**): Argentina-Chile 345 kV Interandes; Argentina-Uruguay 500 kV Salto Grande; Argentina-Brazil Garabí converters (about 2.2 GW); Brazil-Paraguay Itaipú (50/60 Hz, HVDC to Ibiúna); Colombia-Ecuador 230 kV; Peru-Ecuador 220 kV; Panama-Colombia HVDC project (no final investment decision as of July 2026).

## 5. Limits to keep visible

- A drawn layer, not a model: no topology (line ends are not resolved), no parameters, no demand. Brazil's flow network (section 6) has topology and line parameters, but still no demand, dispatch or people, and it is not wired to the engine.
- Brazil runs at 60 Hz. The frequency engine has Chile's constants (50 Hz, CEN EDAC tables, 25F corridor): they must change before Brazil is simulated.
- HVDC links (Brazil's 600 and 800 kV) are kept apart as `dc_links`: a linear DC flow cannot represent them.
- OSM countries (Bolivia and, for now, Argentina) depend on volunteer mapping and are less complete.
- No source states a licence except ODbL (OSM), CC BY (ONS, geoBoundaries) and the data-portal terms; for the rest the UI cites the publisher.
- The first view still frames Chile; the other countries appear when the user pans. The camera limits were widened to Brazil (`web/src/map/baseMap.ts`).

## 6. Brazil flow network (ONS)

Built by `cascadasen-regional --countries BRA --ons`. The file contract and the readiness levels are in `network-format.md`. This section records the source decisions.

**Sources** (ONS Dados Abertos, CC BY, updated daily; downloaded 2026-11-21, cached in `data/raw/regional/bra/ons_*.csv`):

| File | URL | Used columns |
|---|---|---|
| Lines from 230 kV | `https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/linha_transmissao/LINHA_TRANSMISSAO.csv` | `num_barra_de`, `num_barra_para`, `nom_subestacao_de/para`, `val_niveltensao_kv`, `nom_tipolinha`, `cod_equipamento`, `dat_entradaoperacao`, `dat_desativacao`, `val_comprimento`, `val_resistencia`, `val_reatancia`, `val_shunt`, `val_capacoperlongacomlimit` |
| Busbars from 69 kV | `https://ons-aws-prod-opendata.s3.amazonaws.com/dataset/subestacao/SUBESTACAO.csv` | `num_barra`, `id_subestacao`, `nom_subestacao`, `val_niveltensao`, `val_latitude`, `val_longitude` |

Data dictionaries: `DicionarioDados_Linha_Transmissao.{json,pdf}` and `DicionarioDados_Subestacao_Rede_de_Operacao.{json,pdf}` in the same folders.

**Units.** Neither dictionary, JSON or PDF, states the unit of r, x or shunt; length is km and the four main capacity columns are amperes. The magnitudes fit **percent on a 100 MVA base for `val_resistencia` and `val_reatancia`, and Mvar at nominal voltage for `val_shunt`**, the convention of ONS's ANAREDE program. Converted, the median x per circuit-km is:

| kV | x (ohm/km) | r (ohm/km) | Shunt (Mvar/km) |
|---|---|---|---|
| 230 | 0.481 | 0.082 | 0.18 |
| 345 | 0.369 | 0.035 | 0.53 |
| 440 | 0.310 | 0.025 | 1.00 |
| 500 | 0.276 | 0.018 | 1.45 |
| 525 | 0.313 | 0.021 | 1.43 |
| 765 | 0.336 | 0.014 | 2.87 |

All of them are textbook overhead-line values. Read as ohm, x would be about 0.01 to 0.1 ohm/km, far below any overhead line. `test_ons_network.py` fails if the medians leave `X_PER_KM`.

**Decisions** (2026-11-21, with Ricardo):
- **Thermal limit.** `val_capacoperlongacomlimit`, long duration with limiting factor. It is lower than the conductor-only value in 154 rows, and it is the operating limit of the whole line.
- **Missing amperes.** 215 circuits; 0 A counts as missing. They use the ONS median MW per circuit at the same kV and are marked `assumed_fields: ["capacity_mw"]`.
- **HVDC.** The 12 `LINHA DC` records go to `dc_links` with `dc: true`, outside `lines`. Their MW (`kV × A` per record) are unverified. Xingu gives 4,200 MW per bipole against 4,000 nominal, but Madeira gives 12,600 MW against 6,300. Itaipu's HVDC states no amperes.
- **Lines in service.** No deactivation date and entry no later than `as_of`, as Chile's `build_year` filter. No active line enters service in the future today.
- **One bus per ONS substation** (`id_subestacao`). Transformers are not in the data, so the 230 kV and 500 kV levels connect only after this fold. Result: one connected component.
- **Coordinates.** ONS first: 853 of 855 substations. The fallback is an EPE substation with the same normalised name and voltage, exact or with similarity ≥ 0.85. It found none of the 2 missing ones (USIBA 230 kV, COL BOA SORTE 2 500 kV), which are listed in the warnings with their 2 lines.
- **Dropped with a warning.**
  - 18 lines whose end is outside the ONS registry: interconnections with Uruguay, Argentina, Paraguay and Venezuela.
  - 5 *ramal* rows with no "to" end.
- **Scope.** The flow model runs from 230 kV, which is what ONS covers. The drawn layer keeps 66 kV.

**Result** (2026-11-21): 853 buses, 1,305 AC lines (1,842 circuits), 4 DC links (12 records) and 495 plant groups.
- **Length:** AC 174,428 circuit-km (−7.9 % against MapYourGrid's 189,308 km), AC+DC 196,456 km (+3.8 %).
- **Coordinate check:** ONS against EPE agree within a median of 50 m on the 582 substations with the same name; 9 are more than 10 km apart.
- **Error of a deduced network** (typical x, typical capacity, distance-snapped topology): `network-format.md` section 3.1.
