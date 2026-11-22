# Grids as documents

A grid is a JSON document the user keeps and edits in the browser. The backend does not hold it. It reads source documents by country from a store (S3 in production), composes the one the user picks and returns it.

## Store layout (`grids/v1/` in the session bucket)

```
manifest.json            schema, built_at, git commit, per-country metadata, per file: key, country, role, bytes, sha256
CHL/                     topology: grid_snapshot, comunas_geometry, node_index, sen_network
                         operating: operating_points, baseline_opf
                         context: outline.geojson, geo/{substations,taps,lines,plants,storage,comunas}.geojson
ARG|BOL|BRA|PER/         context only: lines, substations, plants, outline (display, not simulable)
scenarios/<id>.json      {id, name, point, open_lines, overlay}
```

Roles: `topology` (one per country), `operating` (needs the same bus ids and year as the topology), `context`, `scenario`. Only CHL has a simulable topology. `atlas_sen.html` is not published.

## Grid document (`POST /api/v1/grids/compose`)

Body: `{"point": "feb2025-1500"}` or `{"scenario": "25f"}`. Response: `schema`, `country`, `point`, `year`, `scenario`, `sources` (key and sha256 of each document used), `network` (same shape as `web/public/cache/network-<year>.json`), `operating` (per bus: `gen_mw`, `load_mw`, `sync_mw`, `inertia_mws`, `people`), `open_lines`, `overlay`, `context` (keys, referenced not embedded).

Errors: 404 unknown point or scenario, 422 bad body, 503 no catalogue published or a document that does not match its checksum.
`overlay` is returned as stored. The simulator applies it (`domain/cascade/overlay.py`); compose does not.

## Publish

```
cascadasen-grids publish --dry-run                       # plan
cascadasen-grids publish                                 # data/grids (git-ignored)
cascadasen-grids verify
cascadasen-grids publish --store s3 --bucket <bucket> --yes   # needs AWS credentials in the environment or --profile
cascadasen-grids verify --store s3 --bucket <bucket>
```

Publish refuses a non-empty destination and `write` never overwrites. The manifest is written last. A new version is a new prefix (`--prefix grids/v2`).

## Settings

`CASCADASEN_GRIDS_STORE` (`local` reads `data/grids`, `s3`), `CASCADASEN_GRIDS_BUCKET` (default: the session bucket), `CASCADASEN_GRIDS_PREFIX` (`grids/v1`).

## AWS resources

The existing bucket `cascadasen-sessions-402909940511`, prefix `grids/v1/`. The task role needs `s3:GetObject` on `grids/*` (it only has `sessions/*` and `runs/*`); until then production runs with `local`. No Terraform yet.
