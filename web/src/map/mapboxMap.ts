import { MapboxOverlay } from "@deck.gl/mapbox";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { loadGridDataWorkflow } from "./gridData";
import { SEN_BOUNDS, PITCH_DEGREES, MAPBOX_STYLE } from "./constants";
import { buildGridLayers } from "./layers";
import { mountChileMapWorkflow } from "./chileMap";
import { createNodePopup } from "./nodeDetail";
import { gridTooltip } from "./tooltip";

const PANEL_CLEARANCE_PX = 400;

/** Why: mapa2 puts the grid on a vector Mapbox basemap with 3D, and falls back to the offline map without a token. */
export function mountMapboxMapWorkflow(container: HTMLDivElement): () => void {
  const token = import.meta.env.VITE_MAPBOX_TOKEN as string | undefined;
  if (!token) return _fallbackToOfflineMap(container);
  const map = _createMap(container, token);
  const popup = createNodePopup(container);
  const overlay = new MapboxOverlay({ interleaved: false, layers: [], onClick: popup.onClick, pickingRadius: 6 });
  map.addControl(overlay);
  _drawGridWhenLoaded(overlay);
  return () => { popup.dispose(); map.remove(); };
}

function _fallbackToOfflineMap(container: HTMLDivElement): () => void {
  console.warn("VITE_MAPBOX_TOKEN is not set: showing the offline map. See web/.env.example.");
  return mountChileMapWorkflow(container);
}

function _createMap(container: HTMLDivElement, token: string): mapboxgl.Map {
  mapboxgl.accessToken = token;
  const map = new mapboxgl.Map({
    container,
    style: MAPBOX_STYLE,
    projection: "mercator",
    config: { basemap: { lightPreset: "night" } },
    bounds: SEN_BOUNDS,
    fitBoundsOptions: { padding: { top: 20, bottom: 20, left: 20, right: PANEL_CLEARANCE_PX }, pitch: PITCH_DEGREES },
    pitch: PITCH_DEGREES,
    attributionControl: true,
  });
  return map;
}

function _drawGridWhenLoaded(overlay: MapboxOverlay) {
  loadGridDataWorkflow()
    .then((grid) => overlay.setProps({ layers: buildGridLayers(grid, { withOutline: false }), getTooltip: gridTooltip }))
    .catch((error) => console.error("No se pudo dibujar la red", error));
}
