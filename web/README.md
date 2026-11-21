# web: CascadaSEN frontend

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

## How it is built

| File | Role |
|---|---|
| `src/App.tsx` | Full-screen map plus the floating right panel |
| `src/Legend.tsx` | Right panel: what each colour and height means |
| `src/map/chileMap.ts` | Creates the deck.gl `Deck`, the camera and tooltips |
| `src/map/gridData.ts` | Loads the GeoJSON files and aggregates plants per substation |
| `src/map/layers.ts` | deck.gl layers and colour tables (the legend reads the same tables) |

Data files are imported with Vite `?url` from `../data/processed/`, so they are bundled into the build and the deployed site works offline:

- `data/processed/chile.geojson`: continental Chile by region, simplified to about 60 KB. Rebuild with `data/scripts/build_chile_outline.sh` (needs `curl` and `npx`; downloads the source into the git-ignored `data/raw/`).
- `data/processed/geo/{lines,substations,plants}.geojson`: built by the backend (`backend/README.md`, `uv run cascadasen-build`). The web app only reads them.

## Notes

- Heights are exaggerated so they read at country zoom (about 120 m per MW and 30 m per kV). They are not physical.
- The app passes its own `<canvas>` to deck.gl and removes it on unmount. Without that, React StrictMode's double mount left a stale canvas that pushed the map sideways.
- AWS resources: none. The build is static files; host them on any static hosting. The org repo cannot be connected to Vercel or similar; see the root `README.md` for the mirror setup.
