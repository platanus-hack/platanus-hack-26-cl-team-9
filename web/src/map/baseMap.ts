import { Deck, MapView, WebMercatorViewport, type Layer, type MapViewState, type PickingInfo } from "@deck.gl/core";
import { GeoJsonLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import chileUrl from "../../../data/processed/chile.geojson?url";
import { SEN_BOUNDS, PITCH_DEGREES, MAPBOX_STYLE } from "./constants";
import { landOf, nearLand, viewportRadiusDeg, type Land } from "./regionLimit";

// Experiment: keep the camera near Chile and drop heavy Standard-style features. `?limite=0` turns it all off to compare.
const LIMITED = new URLSearchParams(location.search).get("limite") !== "0";
const MAX_BOUNDS: [[number, number], [number, number]] = [[-85, -60], [-55, -10]];
const MIN_ZOOM = 4;
const MAX_ZOOM = 13;
// Countries the camera may look at: its center must stay on land (or near it, scaled to the viewport). Add other countries' outlines here.
const LAND_URLS = [chileUrl];
const LAND_MARGIN = 0.25; // fraction of the shorter viewport side the center may be offshore
const LITE_BASEMAP = { show3dObjects: false, showPointOfInterestLabels: false, showTransitLabels: false, showPedestrianRoads: false };
const PANEL_CLEARANCE_PX = 640; // rail + floating panel on the left (see .shell in styles.css)

export type ViewMode = "2d" | "3d";
export interface BaseMap { setLayers(layers: Layer[]): void; setMode(mode: ViewMode): void; zoomBy(delta: number): void; dispose(): void }
const pitchOf = (mode: ViewMode) => (mode === "2d" ? 0 : PITCH_DEGREES);
export interface Handlers { onClick(info: PickingInfo): void; getTooltip(info: PickingInfo): string | null }

/** Why: the cascade viewer needs the same Mapbox basemap as mapa2 but with layers it swaps every frame; without a token it falls back to the offline outline. */
export function createBaseMap(container: HTMLDivElement, handlers: Handlers): BaseMap {
  const token = import.meta.env.VITE_MAPBOX_TOKEN as string | undefined;
  return token ? _mapboxMap(container, token, handlers) : _offlineMap(container, handlers);
}

function _mapboxMap(container: HTMLDivElement, token: string, handlers: Handlers): BaseMap {
  mapboxgl.accessToken = token;
  const map = new mapboxgl.Map({
    container, style: MAPBOX_STYLE, logoPosition: "bottom-right", // the panel covers the bottom-left corner
     projection: "mercator", config: { basemap: { lightPreset: "night", ...(LIMITED ? LITE_BASEMAP : {}) } },
    ...(LIMITED ? { maxBounds: MAX_BOUNDS, minZoom: MIN_ZOOM, maxZoom: MAX_ZOOM } : {}),
    bounds: SEN_BOUNDS, fitBoundsOptions: { padding: { top: 20, bottom: 20, left: PANEL_CLEARANCE_PX, right: 20 }, pitch: PITCH_DEGREES }, pitch: PITCH_DEGREES,
  });
  if (LIMITED) _keepOverLand(map, container);
  const overlay = new MapboxOverlay({ interleaved: false, layers: [], onClick: handlers.onClick, getTooltip: handlers.getTooltip, pickingRadius: 8 });
  map.addControl(overlay);
  const setMode = (mode: ViewMode) => {
    // 2D is the same map seen from straight above: it cannot be tilted or rotated.
    const flat = mode === "2d"; // a true 2D map cannot be tilted or rotated
    flat ? (map.dragRotate.disable(), map.touchZoomRotate.disableRotation()) : (map.dragRotate.enable(), map.touchZoomRotate.enableRotation());
    map.easeTo({ pitch: pitchOf(mode), bearing: 0, duration: 600 });
  };
  return { setLayers: (layers) => overlay.setProps({ layers }), setMode, zoomBy: (d) => map.easeTo({ zoom: map.getZoom() + d, duration: 300 }), dispose: () => map.remove() };
}

/** Why: zooming into the sea or a neighbour's interior is useless; after each move, a center that is too far from land snaps back to the last valid one. */
function _keepOverLand(map: mapboxgl.Map, container: HTMLDivElement) {
  let land: Land = [];
  let lastGood = map.getCenter();
  Promise.all(LAND_URLS.map((url) => fetch(url).then((r) => r.json()))).then((files) => { land = files.flatMap(landOf); }).catch((e) => console.error("No se pudo cargar el contorno", e));
  map.on("moveend", () => {
    if (!land.length) return;
    const { lng, lat } = map.getCenter();
    const radius = viewportRadiusDeg(map.getZoom(), container.clientWidth, container.clientHeight, LAND_MARGIN);
    if (nearLand(land, lng, lat, radius)) lastGood = map.getCenter();
    else map.easeTo({ center: lastGood, duration: 400 });
  });
}
function _offlineMap(container: HTMLDivElement, handlers: Handlers): BaseMap {
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%";
  container.appendChild(canvas);
  const outline = new GeoJsonLayer({ id: "chile-outline", data: chileUrl, stroked: true, filled: true, getFillColor: [16, 24, 40], getLineColor: [60, 80, 115], lineWidthMinPixels: 1 });
  let viewState: MapViewState = _viewState(container);
  const deck = new Deck({ canvas, views: new MapView({ repeat: false, ...(LIMITED ? { minZoom: MIN_ZOOM, maxZoom: MAX_ZOOM } : {}) }), controller: true, initialViewState: viewState,
    onViewStateChange: ({ viewState: next }) => { viewState = next as MapViewState; }, // the controller owns the camera; keep a copy to change only the pitch
    layers: [outline], getTooltip: handlers.getTooltip, onClick: handlers.onClick, pickingRadius: 8 });
  return {
    setLayers: (layers) => deck.setProps({ layers: [outline, ...layers] }),
    setMode: (mode) => deck.setProps({ controller: { dragRotate: mode === "3d", touchRotate: mode === "3d" }, initialViewState: { ...viewState, pitch: pitchOf(mode), bearing: 0, transitionDuration: 600 } }),
    zoomBy: (d) => deck.setProps({ initialViewState: { ...viewState, zoom: viewState.zoom + d, transitionDuration: 300 } }),
    dispose: () => { deck.finalize(); canvas.remove(); },
  };
}

function _viewState(container: HTMLDivElement) {
  const { clientWidth: width, clientHeight: height } = container;
  const clearance = Math.min(PANEL_CLEARANCE_PX, width / 2);
  const fitted = new WebMercatorViewport({ width: width - clearance, height }).fitBounds(SEN_BOUNDS, { padding: 20 });
  const [longitude] = new WebMercatorViewport({ ...fitted, width, height }).unproject([width / 2 - clearance / 2, height / 2]);
  return { longitude, latitude: fitted.latitude - 1, zoom: fitted.zoom + 0.2, pitch: PITCH_DEGREES, bearing: 0 };
}
