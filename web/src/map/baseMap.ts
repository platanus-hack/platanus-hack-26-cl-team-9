import { Deck, MapView, WebMercatorViewport, type Layer, type MapViewState, type PickingInfo } from "@deck.gl/core";
import { GeoJsonLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import chileUrl from "../../../data/processed/chile.geojson?url";
import { regionalOutlineUrl } from "./regional";
import { landOf, nearLand, viewportRadiusDeg, type Land } from "./regionLimit";

const SEN_BOUNDS: [[number, number], [number, number]] = [[-75.5, -43.8], [-66.5, -17.4]];
// Experiment: keep the camera near Chile and drop heavy Standard-style features. `?limite=0` turns it all off to compare.
const LIMITED = new URLSearchParams(location.search).get("limite") !== "0";
// Wide enough in longitude that the whole country fits at 1440 px (Design v5 shows Arica to Puerto Montt); land snapping does the rest.
const MAX_BOUNDS: [[number, number], [number, number]] = [[-110, -62], [-30, 8]];
const MIN_ZOOM = 4;
const MAX_ZOOM = 13;
// Countries the camera may look at: its center must stay on land (or near it, scaled to the viewport). Add other countries' outlines here.
const LAND_URLS = regionalOutlineUrl ? [chileUrl, regionalOutlineUrl] : [chileUrl];
const LAND_MARGIN = 0.25; // fraction of the shorter viewport side the center may be offshore
const LITE_BASEMAP = { show3dObjects: false, showPointOfInterestLabels: false, showTransitLabels: false, showPedestrianRoads: false };
const PITCH_DEGREES = 45;
// Design v5: flat neutral gray land on a dark gray ground (Electricity Maps look).
const LAND_FILL: [number, number, number] = [58, 59, 63];
const LAND_LINE: [number, number, number] = [84, 86, 91];
const STYLE = "mapbox://styles/mapbox/standard";
const PANEL_CLEARANCE_PX = 664; // nav rail (200) + docked panel (12 + 440) + margin, see .shell in styles.css

export type ViewMode = "2d" | "3d";
export interface Camera { lon: number; lat: number; zoom: number }
export interface BaseMap {
  setLayers(layers: Layer[]): void; setMode(mode: ViewMode): void; zoomBy(delta: number): void; dispose(): void;
  /** Back to the initial camera: the whole country next to the panel. */
  fitAll(): void;
  /** Screen position (px, relative to the map container) of a point, for HTML overlays such as event pins. */
  project(lon: number, lat: number): [number, number];
  camera(): Camera;
  /** True when the basemap draws its own place names (Mapbox); the offline outline has none. */
  hasLabels: boolean;
}
const pitchOf = (mode: ViewMode) => (mode === "2d" ? 0 : PITCH_DEGREES);
export type Tooltip = string | { text: string; style?: Partial<CSSStyleDeclaration> } | null;
/** `onClick` gets the gesture's tapCount (1, 2, ...); see clicks.ts for how each basemap delivers a double click. */
export interface Handlers { onClick(info: PickingInfo, tapCount: number): void; getTooltip(info: PickingInfo): Tooltip; isClickable(info: PickingInfo): boolean }
const tapsOf = (event: unknown) => Number((event as { tapCount?: number } | undefined)?.tapCount ?? 1);

/** Why: the cascade viewer needs the same Mapbox basemap as mapa2 but with layers it swaps every frame; without a token it falls back to the offline outline. */
export function createBaseMap(container: HTMLDivElement, handlers: Handlers, initialMode: ViewMode = "3d"): BaseMap {
  const token = import.meta.env.VITE_MAPBOX_TOKEN as string | undefined;
  return token ? _mapboxMap(container, token, handlers, initialMode) : _offlineMap(container, handlers, initialMode);
}

function _mapboxMap(container: HTMLDivElement, token: string, handlers: Handlers, initialMode: ViewMode): BaseMap {
  mapboxgl.accessToken = token;
  const map = new mapboxgl.Map({
    // Logo and attribution sit bottom-left; styles move that corner right of the timeline card (the legend owns bottom-right).
    container, style: STYLE, logoPosition: "bottom-left", attributionControl: false,
     projection: "mercator", config: { basemap: { lightPreset: "night", theme: "monochrome", ...(LIMITED ? LITE_BASEMAP : {}) } },
    ...(LIMITED ? { maxBounds: MAX_BOUNDS, minZoom: MIN_ZOOM, maxZoom: MAX_ZOOM } : {}),
    pitch: pitchOf(initialMode),
  });
  // The fit's padding stays as the camera padding, so the center (zoom, land check) is the center of the map left visible.
  const fit = (pitch: number, duration: number) => map.fitBounds(SEN_BOUNDS, { padding: { top: 20, bottom: 20, left: PANEL_CLEARANCE_PX, right: 20 }, pitch, bearing: 0, duration });
  fit(pitchOf(initialMode), 0);
  map.addControl(new mapboxgl.AttributionControl({ compact: true }), "bottom-left");
  if (LIMITED) _keepOverLand(map, container);
  // MapboxOverlay forwards Mapbox `click` as a click with tapCount 1 and `dblclick` as a click with tapCount 2
  // (@deck.gl/mapbox dist/mapbox-overlay.js, _handleMouseEvent), so a double click arrives as three clicks.
  const overlay = new MapboxOverlay({ interleaved: false, layers: [], onClick: (info, event) => handlers.onClick(info, tapsOf(event)), getTooltip: handlers.getTooltip, pickingRadius: 8,
    // The overlay's own cursor goes on a container with pointer-events none, so it never shows; set it on the map canvas.
    onHover: (info) => { map.getCanvas().style.cursor = handlers.isClickable(info) ? "pointer" : ""; } });
  map.addControl(overlay);
  // A double click on a line cuts it, so it must not also zoom. On empty map double-click zoom stays. Touch double tap
  // zooms in a separate handler that cannot be stopped per target, so touch screens lose double-tap zoom (pinch remains).
  if (matchMedia("(any-pointer: coarse)").matches) map.doubleClickZoom.disable();
  map.on("dblclick", (e) => {
    try {
      const info = overlay.pickObject({ x: e.point.x, y: e.point.y, radius: 8 });
      if (info && handlers.isClickable(info)) e.preventDefault(); // stops ClickZoomHandler (MapMouseEvent.preventDefault)
    } catch { /* picking unavailable: keep the default zoom */ }
  });
  const setMode = (mode: ViewMode) => {
    // 2D is the same map seen from straight above: it cannot be tilted or rotated.
    const flat = mode === "2d"; // a true 2D map cannot be tilted or rotated
    flat ? (map.dragRotate.disable(), map.touchZoomRotate.disableRotation()) : (map.dragRotate.enable(), map.touchZoomRotate.enableRotation());
    map.easeTo({ pitch: pitchOf(mode), bearing: 0, duration: 600 });
  };
  return {
    setLayers: (layers) => overlay.setProps({ layers }), setMode, zoomBy: (d) => map.easeTo({ zoom: map.getZoom() + d, duration: 300 }), dispose: () => map.remove(),
    fitAll: () => fit(map.getPitch(), 600),
    project: (lon, lat) => { const p = map.project([lon, lat]); return [p.x, p.y]; },
    camera: () => { const c = map.getCenter(); return { lon: c.lng, lat: c.lat, zoom: map.getZoom() }; },
    hasLabels: true,
  };
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
function _offlineMap(container: HTMLDivElement, handlers: Handlers, initialMode: ViewMode): BaseMap {
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%";
  container.appendChild(canvas);
  const outline = new GeoJsonLayer({ id: "chile-outline", data: chileUrl, stroked: true, filled: true, getFillColor: LAND_FILL, getLineColor: LAND_LINE, lineWidthMinPixels: 1 });
  const neighbours = regionalOutlineUrl ? [new GeoJsonLayer({ id: "latam-outline", data: regionalOutlineUrl, stroked: true, filled: true, getFillColor: LAND_FILL, getLineColor: LAND_LINE, lineWidthMinPixels: 1 })] : [];
  let viewState: MapViewState = { ..._viewState(container), pitch: pitchOf(initialMode) };
  // Double-click zoom off: then the dblclick recognizer is disabled, `click` has no enabled recognizer to wait for and
  // fires at once on every tap with tapCount 1, 2, ... (@deck.gl/core dist/lib/constants.js RECOGNIZERS, mjolnir.js
  // dist/hammerjs/recognizers/tap.js). With it on, every single click would wait 300 ms.
  const controller = (mode: ViewMode) => ({ doubleClickZoom: false, dragRotate: mode === "3d", touchRotate: mode === "3d" });
  let hovering = false;
  const deck = new Deck({ canvas, views: new MapView({ repeat: false, ...(LIMITED ? { minZoom: MIN_ZOOM, maxZoom: MAX_ZOOM } : {}) }), controller: controller(initialMode), initialViewState: viewState,
    onViewStateChange: ({ viewState: next }) => { viewState = next as MapViewState; }, // the controller owns the camera; keep a copy to change only the pitch
    layers: [...neighbours, outline], getTooltip: handlers.getTooltip, onClick: (info, event) => handlers.onClick(info, tapsOf(event)), pickingRadius: 8,
    onHover: (info) => { hovering = handlers.isClickable(info); }, getCursor: ({ isDragging }) => (isDragging ? "grabbing" : hovering ? "pointer" : "grab") });
  return {
    setLayers: (layers) => deck.setProps({ layers: [...neighbours, outline, ...layers] }),
    setMode: (mode) => deck.setProps({ controller: controller(mode), initialViewState: { ...viewState, pitch: pitchOf(mode), bearing: 0, transitionDuration: 600 } }),
    zoomBy: (d) => deck.setProps({ initialViewState: { ...viewState, zoom: viewState.zoom + d, transitionDuration: 300 } }),
    fitAll: () => deck.setProps({ initialViewState: { ..._viewState(container), pitch: viewState.pitch, transitionDuration: 600 } }),
    dispose: () => { deck.finalize(); canvas.remove(); },
    project: (lon, lat) => {
      const vp = new WebMercatorViewport({ ...viewState, width: container.clientWidth, height: container.clientHeight });
      const [x, y] = vp.project([lon, lat]);
      return [x, y];
    },
    camera: () => ({ lon: viewState.longitude, lat: viewState.latitude, zoom: viewState.zoom }),
    hasLabels: false,
  };
}

function _viewState(container: HTMLDivElement) {
  const { clientWidth: width, clientHeight: height } = container;
  const clearance = Math.min(PANEL_CLEARANCE_PX, width / 2);
  const fitted = new WebMercatorViewport({ width: width - clearance, height }).fitBounds(SEN_BOUNDS, { padding: 20 });
  const [longitude] = new WebMercatorViewport({ ...fitted, width, height }).unproject([width / 2 - clearance / 2, height / 2]);
  return { longitude, latitude: fitted.latitude - 1, zoom: fitted.zoom + 0.2, pitch: PITCH_DEGREES, bearing: 0 };
}
