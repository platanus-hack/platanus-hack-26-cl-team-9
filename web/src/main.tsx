import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { mountChileMapWorkflow } from "./map/chileMap";
import { mountMapboxMapWorkflow } from "./map/mapboxMap";
import { CascadeApp } from "./cascade/CascadeApp";
import "./styles.css";

// ?mapa=2: Mapbox basemap. ?mapa=3: cascade viewer. Default: the offline deck.gl map.
const mapa = new URLSearchParams(location.search).get("mapa");
const mount = mapa === "2" ? mountMapboxMapWorkflow : mountChileMapWorkflow;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {mapa === "3" ? <CascadeApp /> : <App mount={mount} />}
  </StrictMode>,
);
