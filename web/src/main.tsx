import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { mountChileMapWorkflow } from "./map/chileMap";
import { mountMapboxMapWorkflow } from "./map/mapboxMap";
import "./styles.css";

// ?mapa=2 shows the Mapbox basemap; the default is the offline deck.gl map.
const mount = new URLSearchParams(location.search).get("mapa") === "2" ? mountMapboxMapWorkflow : mountChileMapWorkflow;

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App mount={mount} />
  </StrictMode>,
);
