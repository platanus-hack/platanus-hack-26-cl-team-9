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

## Web: "Fuentes de la grilla"

Rail item in mapa 3 (`web/src/cascade/GridSources.tsx`) that opens downward under itself, not in a panel. One row per network in the catalogue (`grids` in `GET /sources`) with a checkbox and its status. **Complete**: the store has its network and operating points, so it can be simulated (Chile). **Partial**: only context to draw (ARG, BOL, BRA, PER). Everything can be unticked, Chile included (the map then draws nothing of it). Ticking one composes the grid at once for the current operating point.

The scenario and the hour are chosen in the rail's "Escenarios", in two folders: **Desastres** (Apagón 25F, plus the cut the user makes on the map) and **Benchmark** (the other operating conditions with no cut: demanda mínima, mediodía solar, punta nocturna). Once a grid is composed, picking one there composes again with the ticked networks.

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
