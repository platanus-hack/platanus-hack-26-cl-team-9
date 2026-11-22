import { Deck, FlyToInterpolator, MapView, WebMercatorViewport, type Layer, type MapViewState, type PickingInfo } from "@deck.gl/core";
import { GeoJsonLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import chileUrl from "../../../data/processed/chile.geojson?url";
import { regionalOutlineUrl } from "./regional";
import type { CameraTarget } from "./countryBounds";

// Until the first network loads: today's Chile frame. Every later target comes from the network's data (countryBounds.ts).
const START_TARGET: CameraTarget = { frame: [[-75.5, -43.8], [-66.5, -17.4]], maxBounds: [[-110, -62], [-30, 8]], land: null };
// Experiment: cap the zoom and drop heavy Standard-style features. `?limite=0` turns it off to compare. The camera itself is free: no bounds, no minimum zoom, no snap-back to land.
const LIMITED = new URLSearchParams(location.search).get("limite") !== "0";
const MAX_ZOOM = 13;
const FLY_MS = 1200;
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
  /** Back to the current target's frame: the whole network next to the panel. */
  fitAll(): void;
  /** Flies to a network's frame (keeping 2D or 3D). The camera is not limited to that country afterwards. */
  setTarget(target: CameraTarget, durationMs?: number): void;
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
    ...(LIMITED ? { maxZoom: MAX_ZOOM } : {}),
    pitch: pitchOf(initialMode),
  });
  // The fit's padding stays as the camera padding, so the center (zoom, land check) is the center of the map left visible.
  const padding = { top: 20, bottom: 20, left: PANEL_CLEARANCE_PX, right: 20 };
  let target = START_TARGET;
  const fit = (duration: number) => map.fitBounds(target.frame, { padding, pitch: map.getPitch(), bearing: 0, duration });
  const setTarget = (next: CameraTarget, duration = FLY_MS) => {
    target = next;
    fit(duration);
  };
  map.addControl(new mapboxgl.AttributionControl({ compact: true }), "bottom-left");
  setTarget(START_TARGET, 0);
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
    } catch (e) { console.warn("picking unavailable, keeping the default zoom", e); /* picking unavailable: keep the default zoom */ }
  });
  const setMode = (mode: ViewMode) => {
    // 2D is the same map seen from straight above: it cannot be tilted or rotated.
    const flat = mode === "2d"; // a true 2D map cannot be tilted or rotated
    flat ? (map.dragRotate.disable(), map.touchZoomRotate.disableRotation()) : (map.dragRotate.enable(), map.touchZoomRotate.enableRotation());
    map.easeTo({ pitch: pitchOf(mode), bearing: 0, duration: 600 });
  };
  return {
    setLayers: (layers) => overlay.setProps({ layers }), setMode, zoomBy: (d) => map.easeTo({ zoom: map.getZoom() + d, duration: 300 }), dispose: () => map.remove(),
    fitAll: () => fit(600), setTarget,
    project: (lon, lat) => { const p = map.project([lon, lat]); return [p.x, p.y]; },
    camera: () => { const c = map.getCenter(); return { lon: c.lng, lat: c.lat, zoom: map.getZoom() }; },
    hasLabels: true,
  };
}

function _offlineMap(container: HTMLDivElement, handlers: Handlers, initialMode: ViewMode): BaseMap {
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%";
  container.appendChild(canvas);
  const outline = new GeoJsonLayer({ id: "chile-outline", data: chileUrl, stroked: true, filled: true, getFillColor: LAND_FILL, getLineColor: LAND_LINE, lineWidthMinPixels: 1 });
  const neighbours = regionalOutlineUrl ? [new GeoJsonLayer({ id: "latam-outline", data: regionalOutlineUrl, stroked: true, filled: true, getFillColor: LAND_FILL, getLineColor: LAND_LINE, lineWidthMinPixels: 1 })] : [];
  let target = START_TARGET;
  let viewState: MapViewState = { ..._viewState(container, target), pitch: pitchOf(initialMode) };
  const view = (t: CameraTarget) => new MapView({ repeat: false, ...(LIMITED ? { maxZoom: MAX_ZOOM } : {}) });
  // Double-click zoom off: then the dblclick recognizer is disabled, `click` has no enabled recognizer to wait for and
  // fires at once on every tap with tapCount 1, 2, ... (@deck.gl/core dist/lib/constants.js RECOGNIZERS, mjolnir.js
  // dist/hammerjs/recognizers/tap.js). With it on, every single click would wait 300 ms.
  const controller = (mode: ViewMode) => ({ doubleClickZoom: false, dragRotate: mode === "3d", touchRotate: mode === "3d" });
  let hovering = false;
  const deck = new Deck({ canvas, views: view(target), controller: controller(initialMode), initialViewState: viewState,
    onViewStateChange: ({ viewState: next }) => { viewState = next as MapViewState; }, // the controller owns the camera; keep a copy to change only the pitch
    layers: [...neighbours, outline], getTooltip: handlers.getTooltip, onClick: (info, event) => handlers.onClick(info, tapsOf(event)), pickingRadius: 8,
    onHover: (info) => { hovering = handlers.isClickable(info); }, getCursor: ({ isDragging }) => (isDragging ? "grabbing" : hovering ? "pointer" : "grab") });
  return {
    setLayers: (layers) => deck.setProps({ layers: [...neighbours, outline, ...layers] }),
    setMode: (mode) => deck.setProps({ controller: controller(mode), initialViewState: { ...viewState, pitch: pitchOf(mode), bearing: 0, transitionDuration: 600 } }),
    zoomBy: (d) => deck.setProps({ initialViewState: { ...viewState, zoom: viewState.zoom + d, transitionDuration: 300 } }),
    fitAll: () => deck.setProps({ initialViewState: { ..._tilted(_viewState(container, target), viewState.pitch), transitionDuration: 600 } }),
    setTarget: (next, duration = FLY_MS) => {
      target = next;
      deck.setProps({ views: view(next), initialViewState: { ..._tilted(_viewState(container, next), viewState.pitch), transitionDuration: duration, transitionInterpolator: new FlyToInterpolator() } });
    },
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

// The fit is computed seen from above; tilted, the far half of the frame looks longer, so 3D steps back a little.
const TILT_ZOOM_OUT = 0.4;
const _tilted = (v: ReturnType<typeof _viewState>, pitch = 0) => ({ ...v, pitch, zoom: pitch > 0 ? v.zoom - TILT_ZOOM_OUT : v.zoom });

/** The target's frame fitted in the part of the map the panel leaves visible. */
function _viewState(container: HTMLDivElement, target: CameraTarget) {
  const width = Math.max(container.clientWidth, 1), height = Math.max(container.clientHeight, 1);
  const clearance = Math.min(PANEL_CLEARANCE_PX, width / 2);
  const fitted = new WebMercatorViewport({ width: Math.max(width - clearance, 1), height }).fitBounds(target.frame, { padding: 20 });
  // Move the center half the clearance west, so the fitted frame sits right of the panel. Mercator x is linear in
  // longitude: 512 * 2^zoom px per 360°.
  const longitude = fitted.longitude - ((clearance / 2) * 360) / (512 * 2 ** fitted.zoom);
  return { longitude, latitude: fitted.latitude, zoom: fitted.zoom, pitch: PITCH_DEGREES, bearing: 0 };
}
