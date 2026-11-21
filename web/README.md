# web: Sub50 frontend

Browser app for the demo: a 2D map of Chile with the SEN grid standing in 3D on top (deck.gl). It reads the processed grid files committed in `data/processed/` and contains no physics, as `docs/stack.md` requires. Every number on screen comes from those files.

## Run locally (guide for people and agents)

Requirements: Node 20 or newer and npm. Tested with Node 22.23 and npm 10.9 on macOS. No backend, API key, cloud account or internet connection is needed once dependencies are installed.

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

Click a line to cut it and replay the cascade computed by the engine (`docs/engine.md`). It reads precomputed files from `web/public/cache/`, which is committed (the deployed image has no Python). After changing the engine or the data, regenerate and commit it:

```bash
cd backend && uv run cascadasen-cache      # about 23 MB, 4 hours x 273 cuts, takes a few seconds
```

Deep links: `?mapa=3&point=feb2025-1500&cut=R239` opens the 25F corridor cut. It uses Mapbox when `VITE_MAPBOX_TOKEN` is set and the offline outline otherwise.

Mapa 3 keeps the camera near Chile (`maxBounds` about lon -85 to -55, lat -60 to -10; zoom 4 to 13, constants in `src/map/baseMap.ts`) and turns off 3D buildings, points of interest, transit and pedestrian roads in the Mapbox Standard style. Add `?limite=0` to remove all of it and compare performance.

## How it is built

| File | Role |
|---|---|
| `src/App.tsx` | Full-screen map plus the floating right panel |
| `src/Legend.tsx` | Right panel: what each colour and height means |
| `src/map/chileMap.ts` | Offline map: creates the deck.gl `Deck`, the camera and tooltips |
| `src/map/mapboxMap.ts` | `?mapa=2`: Mapbox basemap with deck.gl on top (`MapboxOverlay`) |
| `src/map/gridData.ts` | Loads the GeoJSON files and aggregates plants per substation |
| `src/map/layers.ts` | deck.gl layers and colour tables (the legend reads the same tables) |

Data files are imported with Vite `?url` from `../data/processed/`, so they are bundled into the build and the deployed site works offline:

- `data/processed/chile.geojson`: continental Chile by region, simplified to about 60 KB. Rebuild with `data/scripts/build_chile_outline.sh` (needs `curl` and `npx`; downloads the source into the git-ignored `data/raw/`).
- `data/processed/geo/{lines,substations,plants}.geojson`: built by the backend (`backend/README.md`, `uv run cascadasen-build`). The web app only reads them.

## Notes

- Heights are exaggerated so they read at country zoom (about 120 m per MW and 30 m per kV). They are not physical.
- The app passes its own `<canvas>` to deck.gl and removes it on unmount. Without that, React StrictMode's double mount left a stale canvas that pushed the map sideways.
- AWS resources: none. The build is static files; host them on any static hosting. The org repo cannot be connected to Vercel or similar; see the root `README.md` for the mirror setup.
