# Datasets

Last updated: 2026-11-21. Status labels: **verified** (opened or downloaded and checked in this project), **not verified** (listed in earlier research, not checked), **missing** (no source found yet).

## 1. Summary

| Dataset | Needed for | Source | Status |
|---|---|---|---|
| Power plants (location, MW, technology) | Generator columns, node generation | IDE Energia MapServer layers 1-6 | **Verified, downloaded** (1,193 operating SEN plants, 37,964 MW installed) |
| Transmission lines (geometry, kV, length, circuits, name) | Line layer, network edges | IDE Energia layer 10 | **Verified (fields), not downloaded** |
| Substations | Nodes | IDE Energia layer 8 | Layer exists, fields not checked, not downloaded |
| Energy storage (batteries) | "What would have prevented it" | IDE Energia layer 9 | Layer exists, fields not checked, not downloaded |
| Line reactance and thermal limit | Power flow, overload rule | Not in IDE Energia or Infotecnica | **Missing**. See section 4 |
| Scenario generation and demand per node | Scenarios | CEN operation base Oct 2026 (zip) | Zip opens; content of the spreadsheets not checked |
| 25F figures for validation | Tests | CEN and university reports | **Verified** (see `plan.md` section 5) |
| Chile outline / regions | Base map | Natural Earth admin-1 or IDE Chile / BCN | Not downloaded |
| Population per region / commune | "People without power" | INE Census 2024 | Not downloaded |
| Commune centroids / main cities | City lights | INE / BCN or a manual list of ~25 cities | Not downloaded |
| Plant -> node assignment | Network build | Own work | Not done |

Nothing from this project is committed to the repo yet. The downloaded files live outside it (see section 2.3) and can be regenerated with the scripts in the appendices.

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

A previous session wrote these under `/Users/alonsoutreras/Desktop/Hackathon/cascadasen/datos/` on Alonso's machine (outside this repo):
- `raw/centrales_{bioenergia,eolicas,geotermicas,hidroelectricas,solares,termoelectricas}.geojson`
- `centrales_sen.geojson`: 1,193 operating SEN plants with fields `nombre, tecnologia, mw, combustible, propietario, region_cod, region, comuna_cod, fuente`.

To get them in the repo, copy those files into `data/` or regenerate with Appendix A and B. Raw files are about 800 KB; the unified file is about 430 KB, small enough to commit. Licence and terms of use of the IDE Energia data were not checked.

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
- Line capacity for corridors other than the 25F one: the CEN transmission-restrictions study may have it; current version not verified.

## 5. Plant -> node assignment (task)

The engine has about 10-14 nodes. Every plant in `centrales_sen.geojson` must be assigned to a node by the nearest substation or by zone polygon, and node generation per scenario is built from the assigned plants. Document the rule. This step has not been done.

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
| 29 | INE Census 2024 | https://censo2024.ine.gob.cl/resultados/ | Page verified; figures not extracted |
| - | Article by CEN engineers on the 25F protection sequence | https://www.pacw.org/chilean-grid-blackout-of-february-2025 | Read by the evaluator |
| - | Andes (similar hackathon project, click-to-fail) | https://github.com/aleetreny/Encode | Verified |
| - | COSMIC (MATLAB dynamic cascade simulator) | https://github.com/ecotillasanchez/cosmic | Verified |
| - | pypsa-chile, PyPSA-CL | https://github.com/sanjaygrr/pypsa-chile , https://github.com/paredes-vergara/PyPSA-CL | Verified (economic dispatch, not security) |

Numbering follows the team's earlier research notes; gaps are sources not needed here.

## Appendix A: download script (`data/scripts/descargar_centrales.py`)

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
