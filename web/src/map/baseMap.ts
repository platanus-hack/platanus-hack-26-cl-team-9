import { Deck, MapView, WebMercatorViewport, type Layer, type PickingInfo } from "@deck.gl/core";
import { GeoJsonLayer } from "@deck.gl/layers";
import { MapboxOverlay } from "@deck.gl/mapbox";
import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import chileUrl from "../../../data/processed/chile.geojson?url";

const SEN_BOUNDS: [[number, number], [number, number]] = [[-75.5, -43.8], [-66.5, -17.4]];
const PITCH_DEGREES = 45;
const PANEL_CLEARANCE_PX = 460;

export interface BaseMap { setLayers(layers: Layer[]): void; dispose(): void }
export interface Handlers { onClick(info: PickingInfo): void; getTooltip(info: PickingInfo): string | null }

/** Why: the cascade viewer needs the same Mapbox basemap as mapa2 but with layers it swaps every frame; without a token it falls back to the offline outline. */
export function createBaseMap(container: HTMLDivElement, handlers: Handlers): BaseMap {
  const token = import.meta.env.VITE_MAPBOX_TOKEN as string | undefined;
  return token ? _mapboxMap(container, token, handlers) : _offlineMap(container, handlers);
}

function _mapboxMap(container: HTMLDivElement, token: string, handlers: Handlers): BaseMap {
  mapboxgl.accessToken = token;
  const map = new mapboxgl.Map({
    container, style: "mapbox://styles/mapbox/standard", projection: "mercator", config: { basemap: { lightPreset: "night" } },
    bounds: SEN_BOUNDS, fitBoundsOptions: { padding: { top: 20, bottom: 20, left: 20, right: PANEL_CLEARANCE_PX }, pitch: PITCH_DEGREES }, pitch: PITCH_DEGREES,
  });
  const overlay = new MapboxOverlay({ interleaved: false, layers: [], onClick: handlers.onClick, getTooltip: handlers.getTooltip, pickingRadius: 8 });
  map.addControl(overlay);
  return { setLayers: (layers) => overlay.setProps({ layers }), dispose: () => map.remove() };
}

function _offlineMap(container: HTMLDivElement, handlers: Handlers): BaseMap {
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%";
  container.appendChild(canvas);
  const outline = new GeoJsonLayer({ id: "chile-outline", data: chileUrl, stroked: true, filled: true, getFillColor: [16, 24, 40], getLineColor: [60, 80, 115], lineWidthMinPixels: 1 });
  const deck = new Deck({ canvas, views: new MapView({ repeat: false }), controller: true, initialViewState: _viewState(container),
    layers: [outline], getTooltip: handlers.getTooltip, onClick: handlers.onClick, pickingRadius: 8 });
  return { setLayers: (layers) => deck.setProps({ layers: [outline, ...layers] }), dispose: () => { deck.finalize(); canvas.remove(); } };
}

function _viewState(container: HTMLDivElement) {
  const { clientWidth: width, clientHeight: height } = container;
  const clearance = Math.min(PANEL_CLEARANCE_PX, width / 2);
  const fitted = new WebMercatorViewport({ width: width - clearance, height }).fitBounds(SEN_BOUNDS, { padding: 20 });
  const [longitude] = new WebMercatorViewport({ ...fitted, width, height }).unproject([width / 2 + clearance / 2, height / 2]);
  return { longitude, latitude: fitted.latitude - 1, zoom: fitted.zoom + 0.2, pitch: PITCH_DEGREES, bearing: 0 };
}
