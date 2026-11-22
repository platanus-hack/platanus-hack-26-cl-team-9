# Grids as documents

A grid is a JSON document the user keeps and edits in the browser. The backend does not hold it. `cascadasen-grids publish` converts `data/processed` once into the documents the app reads, organised by country. Composing a grid only picks and joins them: a request never runs the engine or reads the raw snapshot.

## Store layout (`grids/v2/` in the session bucket)

```
manifest.json                    schema, built_at, git commit, per-country metadata; per file: key, country, role, bytes, sha256, meta
CHL/network-<year>.json          role network: {year, nodes, lines}, same shape as web/public/cache/network-<year>.json
CHL/operating/<point>.json       role operating: {point, label, year, snapshot, buses: {B###: gen_mw, load_mw, sync_mw, inertia_mws, people}}
ARG|BOL|BRA|PER/grid.json        role context: {meta, lines, substations, plants} in the shape of web/src/map/regional.ts
scenarios/<id>.json              role scenario: {id, name, point, open_lines, overlay}
<ISO>/source/...                 role source: the raw files (snapshot, geojson, outlines), kept for traceability; the app does not read them
```

Why whole documents per country: what the user edits is an element (a line, a substation, a plant), and elements reference each other (line to buses, operating point to buses). One document per country keeps those references together. Showing or hiding a layer is a filter in the web. The network and the operating point stay apart because the user changes the point without changing the network; compose checks that both cover the same buses and year.

Only CHL is simulable. The other countries are display-only context. `atlas_sen.html` is not published. `grids/v1/` (first layout, raw files only) is superseded and can be deleted by hand.

## API

- `GET /api/v1/grids/sources`: `grids` (country, name, status Complete or Partial, context key), `points`, `scenarios`, `context`, `documents`, `built_at`.
- `POST /api/v1/grids/compose`: body `{point | scenario, context?: [keys]}` (`context` omitted: all, `[]`: none). Returns `schema`, `country`, `point`, `year`, `scenario`, `sources` (key and sha256), `network`, `operating`, `open_lines`, `overlay`, `context` (keys).
- `GET /api/v1/grids/documents/<key>`: one context document, checked against its sha256.
- Errors: 404 unknown point, scenario or document; 422 bad body, unknown context key, or network and point that do not fit; 503 no catalogue or a document that does not match its checksum.
- `overlay` is returned as stored. The simulator applies it (`domain/cascade/overlay.py`); compose does not.

## Simulate with several changes (`POST /api/v1/grids/simulate`)

Body `{point, open_lines: [R###], out_buses: [B###]}`, at most 50 changes in all, rate-limited like the session cuts. Stateless: the same request gives the same timeline. `application/grid_simulation.py` (`GridSimulator`) takes the operating point from the processed world (the same one the sessions use, not from the grid documents), takes the substations out of service with the overlay (`in_service: false`), and runs the cascade with all the open lines at once. The timeline carries the failure cost in `summary` (recomputed after adding the direct loss of substations out of service) and `health`, the after-cut index with its cost (`health.md` "Cost").

Response: `timeline` (same shape as `web/public/cache/<point>/<cut>.json`), `open_lines`, `out_buses`, `dropped_lines` (lines that went with their substation: they are out already), `direct` (the load, generation and people the outage itself removes) and `warnings`. A substation out of service is dark in every frame, and its people and load are added to the summary. ASSUMPTION: the engine drops that bus before the cascade, so the cascade does not count it twice. Errors: 404 unknown point, line or substation; 422 no changes, more than 50, or an invalid overlay; 429 rate limit.

The web (docs/mapa3.md, tab "Estado de la red") calls it only for two or more changes. The committed cache and this endpoint run the same engine; `test_the_committed_cache_matches_the_engine_for_a_single_cut` fails when the engine changes and the cache was not regenerated (`cascadasen-cache`).

## Web: "Fuentes de la grilla"

Rail item in mapa 3 (`web/src/cascade/GridSources.tsx`) that opens downward under itself, not in a panel. One row per network in the catalogue (`grids` in `GET /sources`) with a radio button and its status. **Complete**: the store has its network and operating points, so it can be simulated (Chile). **Partial**: only drawn (ARG, BOL, BRA, PER). One network is on the map at a time (issue #49, decided 2026-11-22): a row is a choice, not a tick, and the marked row is the network on the map, the same one the panel header names (`mapa3.md` section 4.1). Choosing Chile composes it with no context (`context: []`). Choosing another country composes `context: [<its key>]`, and the map shows only that country, view only; Chile's changes stay and come back with Chile. A click on the marked row composes it from the store when it came from the app files. **Volver a la caché** returns to the app files. Choosing a network in the panel header also returns to the app files.

The scenario and the hour are chosen in the rail's "Escenarios", in two folders: **Desastres** (Apagón 25F) and **Benchmark** (the other operating conditions: demanda mínima, mediodía solar, punta nocturna). The cuts the user makes are not scenarios: they go to the tab "Estado de la red". A Benchmark entry keeps those changes at the new hour; Apagón 25F replaces them with its cut. Once Chile is composed, picking a scenario there composes Chile again at the new hour.

The map shows the composed network, buses and context; the cascade timelines still come from the app cache for the same point and cut (`web/public/cache`). "Volver a la caché" returns to the cache. Locked inside a shared session.

## Publish

```
cascadasen-grids publish --dry-run                       # plan
cascadasen-grids publish                                 # data/grids (git-ignored)
cascadasen-grids verify
cascadasen-grids publish --store s3 --bucket <bucket> --yes   # AWS credentials in the environment or --profile
cascadasen-grids verify --store s3 --bucket <bucket>
```

Publish refuses a non-empty destination and `write` never overwrites. The manifest is written last. A new layout is a new prefix (`--prefix grids/v3`).

## Settings

`CASCADASEN_GRIDS_STORE` (`local` reads `data/grids`, `s3`), `CASCADASEN_GRIDS_BUCKET` (default: the session bucket), `CASCADASEN_GRIDS_PREFIX` (`grids/v2`). Local web: run the API with the default store after `cascadasen-grids publish`; Vite proxies `/api` to it.

## AWS resources

The existing bucket `cascadasen-sessions-402909940511`, prefix `grids/v2/`. The task role `cascadasen-task` has `s3:GetObject` on `grids/*` through the inline policy `cascadasen-task-grids`, added by hand (not in Terraform). Production also needs `CASCADASEN_GRIDS_STORE=s3` in the task definition.
