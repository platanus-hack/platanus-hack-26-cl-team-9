import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { mountChileMapWorkflow } from "./map/chileMap";
import { mountMapboxMapWorkflow } from "./map/mapboxMap";
import { CascadeApp } from "./cascade/CascadeApp";
import "./styles.css";

// Mapa 3 (cascade viewer) is the main map: `/` and `?mapa=3`.
// Deprecated, kept for reference only: ?mapa=1 (offline deck.gl map) and ?mapa=2 (Mapbox basemap).
const mapa = new URLSearchParams(location.search).get("mapa");
const legacy = mapa === "1" || mapa === "2";
if (legacy) console.warn(`?mapa=${mapa} is deprecated: use / (mapa 3), the main map.`);
const mount = mapa === "2" ? mountMapboxMapWorkflow : mountChileMapWorkflow;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {legacy ? <App mount={mount} /> : <CascadeApp />}
  </StrictMode>,
);
