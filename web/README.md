# web: Sub50 frontend

Browser app for the demo: a 2D map of Chile with the SEN grid standing in 3D on top (deck.gl). It reads the processed grid files committed in `data/processed/` and contains no physics, as `docs/stack.md` requires. Every number on screen comes from those files.

## Run locally (guide for people and agents)

Requirements: Node 20 or newer and npm. Tested with Node 22.23 and npm 10.9 on macOS. No backend, API key, cloud account or internet connection is needed once dependencies are installed, except for session mode (`?sesion=`), which needs the backend.

```bash
cd web
npm install        # first time only
npm run dev        # http://localhost:5173
```

Other commands:

| Command | What it does |
|---|---|
| `npm test` | Vitest unit tests (`src/**/*.test.ts`) |
| `npm run build` | Type check (`tsc --noEmit`) and production build into `web/dist/` |
| `npm run preview` | Serve `web/dist/` at http://localhost:4173 |

Checks an agent should run before committing: `npx tsc --noEmit`, `npm test` and `npm run build`. All three must pass.

To stop a dev server started in the background: `pkill -f "vite"`.

## Maps (1 and 2 are deprecated)

`/` is mapa 3, the main map (below). The two maps in this table are deprecated and kept as reference.

| URL | Map | Needs internet |
|---|---|---|
| `http://localhost:5173/?mapa=1` (deprecated) | deck.gl with the light Chile outline | No |
| `http://localhost:5173/?mapa=2` (deprecated) | Mapbox vector basemap (Standard, night) with the same grid layers on top | Yes, to load the tiles |

`?mapa=2` reads a public Mapbox token from `web/.env.local` (git-ignored):

```bash
cp .env.example .env.local   # then set VITE_MAPBOX_TOKEN=pk....
```

Restart `npm run dev` after changing it. Without a token, `?mapa=2` falls back to the offline map. Restrict the token by URL in the Mapbox account: Vite puts it in the browser bundle.

## Mapa 3: cascade viewer (main map, `/`)

Mapa 3 is the main map and opens at `/` (also `?mapa=3`). Mapas 1 and 2 are **deprecated**: they stay only as reference and log a warning in the console.

Full guide, actors and legend: [`docs/mapa3.md`](../docs/mapa3.md). Minimum dataset: [`docs/minimum-dataset.md`](../docs/minimum-dataset.md).

The interface follows the Paper "Design v5" frames (`docs/design.md` section 3.2) with the Design v6 changes (section 3.3): a nav rail whose Escenarios tree lists each scenario (a cut) with its operating conditions, a docked panel with the Red and Simulación tabs, a timeline card with numbered events and island frequencies, and a legend that switches between voltage (cold colors) and load (green, yellow, orange, red). Usage: `docs/mapa3.md` section 4.

Click a line or substation to see its detail; click the selected element again (or use "Sacar de servicio" / "Apagar subestación" in its card) to switch it off and replay the cascade computed by the engine (`docs/engine.md`); a substation goes out of service with its demand and generation (in a shared session, all its lines open). A fast double click does nothing (`docs/mapa3.md` sections 4 and 11). It reads precomputed files from `web/public/cache/`, which is committed (the deployed image has no Python). After changing the engine or the data, regenerate and commit it:

```bash
cd backend && uv run cascadasen-cache      # about 46 MB, 4 hours x (273 line cuts + 188 substation shutdowns + `health.json`), about a minute
```

Session mode: `?sesion=<sid>` (or the **Sesión compartida** rail item) opens a shared, editable copy of the network served by the backend; the **Datos** tab edits buses, lines, generators, loads and datacenters, and every client of the session sees the changes live (SSE, with a 2 s polling fallback). Guide: [`docs/mapa3.md`](../docs/mapa3.md) section 11, API: [`docs/sessions-api.md`](../docs/sessions-api.md). The browser calls `/api`, which `npm run dev` proxies to `VITE_API_TARGET` (default `http://localhost:8000`, start it with `cd backend && uv run cascadasen-api`; docker compose sets `http://backend:8000`). Without `?sesion=` the app makes no `/api` request and needs no backend.

Assistant: the **Asistente** rail item opens a chat where you ask in natural language ("Agrega un datacenter de 120 MW en Antofagasta y corta R014") and see each step of the model live: what it writes, each tool call with its state and result, and the final reply. The map joins the session the assistant edits and refreshes after each tool. It needs the backend with `CASCADASEN_LLM_ENABLED=true` and a Bedrock model (`docs/assistant.md` section 1); otherwise the panel says the assistant is not enabled. The conversation id is kept in `localStorage` (`sub50.assistant.cid`). Details: [`docs/assistant.md`](../docs/assistant.md) section 2c.

Incidents: the **Incidentes** rail item lists the documented incidents (`GET /api/v1/attacks/catalog`, in file order) and simulates one: it creates or reuses a session at the incident's hour, runs it with the chosen policy and outage hours (an assumption), and shows the consequence card, the agents' response (experimental indicators), what would have prevented it, the cycles and both notices. **Ver cascada en el mapa** plays a cycle's cascade with the timeline. It needs the backend. Details: [`docs/mapa3.md`](../docs/mapa3.md) section 4.2.

Deep links: `?mapa=3&point=feb2025-1500&cut=R239` opens the 25F corridor cut. It uses Mapbox when `VITE_MAPBOX_TOKEN` is set and the offline outline otherwise.

Mapa 3 keeps the camera near Chile (`maxBounds` lon -110 to -35, lat -62 to -5, wide enough that the whole country fits at 1440 px; zoom 4 to 13, constants in `src/map/baseMap.ts`) and turns off 3D buildings, points of interest, transit and pedestrian roads in the Mapbox Standard style. The camera center must also stay on land or near it (`src/map/regionLimit.ts`: the margin is a quarter of the shorter viewport side, so it shrinks as you zoom in); after a move that ends too far offshore, the map snaps back to the last valid center. To allow another country, add its land GeoJSON URL to `LAND_URLS` in `baseMap.ts`. Add `?limite=0` to remove all of it and compare performance.

## How it is built

| File | Role |
|---|---|
| `src/cascade/` | Mapa 3: the Design v5 shell, cascade playback and its styles (`cascade.css`); file list in `docs/mapa3.md` section 8 |
| `src/map/baseMap.ts` | Mapa 3 basemap: Mapbox Standard (night, monochrome) or the offline outline, camera fit, projection for HTML overlays |
| `src/App.tsx` | Deprecated mapas 1 and 2: full-screen map plus the floating right panel |
| `src/Legend.tsx` | Right panel: what each colour and height means |
| `src/map/chileMap.ts` | Offline map: creates the deck.gl `Deck`, the camera and tooltips |
| `src/map/mapboxMap.ts` | `?mapa=2`: Mapbox basemap with deck.gl on top (`MapboxOverlay`) |
| `src/map/gridData.ts` | Loads the GeoJSON files and aggregates plants per substation |
| `src/map/layers.ts` | deck.gl layers and colour tables (the legend reads the same tables) |
| `src/session/sessionApi.ts` | Sessions API client: typed calls, `ApiError`, `sessionIdFrom`, `subscribe` (SSE or polling) |
| `src/session/useSession.ts`, `loader.ts`, `SessionBar.tsx`, `SessionCut.tsx`, `DataPanel.tsx`, `session.css` | Session state and refetch, the **Sesión compartida** view and panel-head strip, the open lines in **Simulación**, the **Datos** tab, and their styles |
| `src/assistant/` | In-app assistant chat (**Asistente** rail item): SSE parser, event reducer, Spanish labels, API client, `useAssistant` hook and the panel; see `docs/assistant.md` section 2c |
| `src/incidents/` | Documented incidents (**Incidentes** rail item): pure helpers (`incidents.ts`), the `useIncident` hook owned by `CascadeApp`, the panel and its styles; see `docs/mapa3.md` section 4.2 |
| `src/session/geo.ts` | Nearest bus of at least 220 kV (great-circle distance only, no physics) |

Data files are imported with Vite `?url` from `../data/processed/`, so they are bundled into the build and the deployed site works offline:

- `data/processed/chile.geojson`: continental Chile by region, simplified to about 60 KB. Rebuild with `data/scripts/build_chile_outline.sh` (needs `curl` and `npx`; downloads the source into the git-ignored `data/raw/`).
- `data/processed/geo/{lines,substations,plants}.geojson`: built by the backend (`backend/README.md`, `uv run cascadasen-build`). The web app only reads them.

## Notes

- Heights are exaggerated so they read at country zoom (about 120 m per MW and 30 m per kV). They are not physical.
- The app passes its own `<canvas>` to deck.gl and removes it on unmount. Without that, React StrictMode's double mount left a stale canvas that pushed the map sideways.
- AWS resources: none. The build is static files; host them on any static hosting. The org repo cannot be connected to Vercel or similar; see the root `README.md` for the mirror setup.
