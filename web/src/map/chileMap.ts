import { Deck, MapView, WebMercatorViewport, type PickingInfo } from "@deck.gl/core";
import { loadGridDataWorkflow } from "./gridData";
import { buildGridLayers } from "./layers";

// The SEN runs Arica to Chiloe; frame it first. Aysen and Magallanes stay reachable by panning.
const SEN_BOUNDS: [[number, number], [number, number]] = [[-75.5, -43.8], [-66.5, -17.4]];
const MAP_PITCH_DEGREES = 45;
// Keep Chile clear of the floating panel on the right (styles.css .panels: 360px + 16px margin).
const PANEL_CLEARANCE_PX = 400;

/** Why: the demo's base is a good 2D map of Chile with the grid elements in 3D on top. */
export function mountChileMapWorkflow(container: HTMLDivElement): () => void {
  const deck = _createDeck(container);
  _drawGridWhenLoaded(deck);
  return () => _destroyDeck(deck);
}

function _createDeck(container: HTMLDivElement): Deck<MapView> {
  return new Deck({
    canvas: _appendCanvas(container),
    views: new MapView({ repeat: false }),
    controller: true,
    initialViewState: _viewStateFitting(container),
    getTooltip: _tooltip,
  });
}

// We own the canvas: deck.gl creates its own asynchronously, so after React StrictMode's double
// mount a stale one stayed in the DOM, pushed the live one sideways and the map looked cut.
function _destroyDeck(deck: Deck<MapView>) {
  const canvas = deck.props.canvas as HTMLCanvasElement;
  deck.finalize();
  canvas.remove();
}

function _appendCanvas(container: HTMLDivElement): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%";
  container.appendChild(canvas);
  return canvas;
}

function _drawGridWhenLoaded(deck: Deck<MapView>) {
  loadGridDataWorkflow()
    .then((grid) => deck.setProps({ layers: buildGridLayers(grid) }))
    .catch((error) => console.error("No se pudo dibujar la red", error));
}

// Fit the SEN in the free area left of the panel, then tilt so the columns read as 3D.
function _viewStateFitting(container: HTMLDivElement) {
  const { clientWidth: width, clientHeight: height } = container;
  const clearance = Math.min(PANEL_CLEARANCE_PX, width / 2);
  const fitted = new WebMercatorViewport({ width: width - clearance, height }).fitBounds(SEN_BOUNDS, { padding: 20 });
  // Shift the camera right by half the panel so the fitted area sits left of it on the full-width canvas.
  const [longitude] = new WebMercatorViewport({ ...fitted, width, height }).unproject([width / 2 + clearance / 2, height / 2]);
  return { longitude, latitude: fitted.latitude - 1, zoom: fitted.zoom + 0.2, pitch: MAP_PITCH_DEGREES, bearing: 0 };
}

function _tooltip({ object, layer }: PickingInfo): string | null {
  if (!object || !layer) return null;
  if (layer.id === "generation") return `${object.name}\n${Math.round(object.mw)} MW · ${object.tech}`;
  return `${object.name}\n${object.kv ?? "?"} kV`;
}
