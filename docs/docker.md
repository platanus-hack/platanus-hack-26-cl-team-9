# Running locally with Docker
Last updated: 2026-11-21. Needs only Docker with Compose (Docker Desktop, or Colima on macOS).

```
docker compose up --build        # first run builds both images
docker compose down              # stop
```
| Service | URL | What it is |
|---|---|---|
| `web` | http://localhost:5173 | Vite dev server (npm). `./web` and `./data` are bind-mounted, so edits hot-reload. `node_modules` lives in the container |
| `backend` | http://localhost:8000 | Grid data API (`/docs`, `/map`, `/api/v1/*`). Reads `./data/processed/` mounted at `/data` |

The web app reads the committed files in `data/processed/` and the mapa 3 caches under `web/public/cache/`. The operation mode of mapa 3 (`/?modo=operacion`) also calls the backend: the Vite dev server proxies `/api` to `VITE_API_TARGET` (`http://backend:8000` in compose, `http://localhost:8000` locally), so `web` starts after `backend` is healthy. Without the backend, the operation mode falls back to the precomputed runs in `web/public/cache/theater/` (`uv run cascadasen-sim-fixtures` on the host).

`?mapa=2` (Mapbox basemap) needs a public token. Create `web/.env.local` with `VITE_MAPBOX_TOKEN=pk...` (see `web/.env.example`); it is git-ignored and the bind mount makes it visible in the container. Restart `web` after changing it. Without a token the offline map is used.

Port already in use? Set `WEB_PORT` and `BACKEND_PORT`, for example `WEB_PORT=5180 docker compose up`.

## Optional: rebuild the data
`data/processed/` is committed, so the stack runs offline. To rebuild it from the public sources (needs internet, overwrites committed files):
```
docker compose --profile data run --rm data-build              # uses the cache in data/raw/
docker compose --profile data run --rm data-build cascadasen-build --refresh
```
Restart `backend` or call `POST /api/v1/admin/reload` afterwards.

## Notes
- The backend image uses `uv sync --locked`, so `backend/uv.lock` must be current.
- `web` runs the dev server, not a production build.
- Compose may warn that buildx is missing (Colima); the build still works with the classic builder.

## Optional LLM in Docker

`docker compose` reads `backend/.env` if it exists (only `CASCADASEN_*` settings, never keys). To use the LLM commander with Amazon Bedrock, build with the extra and share your AWS profile read-only:

1. `backend/.env` with `CASCADASEN_LLM_ENABLED=true`, `CASCADASEN_LLM_PROVIDER=bedrock`, `CASCADASEN_AWS_REGION=us-east-1`.
2. Credentials: either export `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN` in the shell that runs compose (they are passed through to `backend`), or set `CASCADASEN_AWS_PROFILE` and uncomment the `${HOME}/.aws:/root/.aws:ro` volume.
3. `WITH_LLM=1 docker compose up --build`.
