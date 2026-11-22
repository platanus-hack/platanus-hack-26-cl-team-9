import { Deck, MapView, WebMercatorViewport, type PickingInfo } from "@deck.gl/core";
import { loadGridDataWorkflow } from "./gridData";
import { SEN_BOUNDS, PITCH_DEGREES } from "./constants";
import { buildGridLayers } from "./layers";
import { createNodePopup } from "./nodeDetail";
import { gridTooltip } from "./tooltip";

// Keep Chile clear of the floating panel on the right (styles.css .panels: 360px + 16px margin).
const PANEL_CLEARANCE_PX = 400;

/** Why: the demo's base is a good 2D map of Chile with the grid elements in 3D on top. */
export function mountChileMapWorkflow(container: HTMLDivElement): () => void {
  const popup = createNodePopup(container);
  const deck = _createDeck(container, popup.onClick);
  _drawGridWhenLoaded(deck);
  return () => { popup.dispose(); _destroyDeck(deck); };
}

function _createDeck(container: HTMLDivElement, onClick: (info: PickingInfo) => void): Deck<MapView> {
  return new Deck({
    canvas: _appendCanvas(container),
    views: new MapView({ repeat: false }),
    controller: true,
    initialViewState: _viewStateFitting(container),
    getTooltip: gridTooltip,
    onClick,
    pickingRadius: 6,
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
  return { longitude, latitude: fitted.latitude - 1, zoom: fitted.zoom + 0.2, pitch: PITCH_DEGREES, bearing: 0 };
}
