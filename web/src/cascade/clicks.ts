/**
 * Map clicks: the first click on a line or substation selects it, a second click on the selected element switches it off.
 * A fast double click never switches anything off. Pure, so it can be tested without a map.
 *
 * The two basemaps deliver a double click differently (see baseMap.ts):
 * - Mapbox (`MapboxOverlay`): three callbacks, `click` (tapCount 1), `click` (tapCount 1), then the DOM `dblclick`
 *   forwarded as a `click` with tapCount 2.
 * - Offline `Deck` with double-click zoom off: two callbacks, tapCount 1 then tapCount 2, each as soon as it happens.
 * Any click with tapCount 2 or more, or within DOUBLE_CLICK_MS of the previous click on the same element, belongs to a
 * double click and does nothing: it neither switches off nor re-selects (after a slow second click has switched a line
 * off and cleared the selection, the OS `dblclick` that trails it must not select the line again).
 */

export type Pick = { kind: "line" | "node"; id: string };
export type ClickAction = { type: "select"; target: Pick } | { type: "toggle"; target: Pick } | { type: "clear" } | { type: "none" };
/** The last click on an element: which one (`kind:id`) and when (ms). */
export interface ClickMemory { key: string | null; at: number }

/** Two clicks on the same element closer than this are a double click, even without tapCount 2 (touch on Mapbox). */
export const DOUBLE_CLICK_MS = 400;
export const NO_CLICK: ClickMemory = { key: null, at: -Infinity };

const keyOf = (p: Pick) => `${p.kind}:${p.id}`;

/**
 * `selection` is the app's current selection, which can also change outside the map (list rows in a card, Cerrar,
 * Escape), so a selection made from the panel is switched off by one map click.
 */
export function interpretClick(target: Pick | null, tapCount: number, at: number, selection: Pick | null, memory: ClickMemory): { action: ClickAction; memory: ClickMemory } {
  if (!target) return { action: { type: "clear" }, memory: NO_CLICK };
  const key = keyOf(target);
  const next = { key, at };
  const fast = memory.key === key && (tapCount >= 2 || at - memory.at <= DOUBLE_CLICK_MS);
  if (fast) return { action: { type: "none" }, memory: next };
  if (!selection || keyOf(selection) !== key) return { action: { type: "select", target }, memory: next };
  if (tapCount >= 2) return { action: { type: "none" }, memory: next };
  return { action: { type: "toggle", target }, memory: next };
}

/** What a picked deck.gl object is, from its layer id. `lines-open` picks `{ line, path }`; the other line layers pick the line. */
export function pickOf(layerId: string, object: unknown): Pick | null {
  const obj = object as { id?: string; line?: { id: string } } | null | undefined;
  const id = obj?.line?.id ?? obj?.id;
  if (!id) return null;
  if (layerId.startsWith("lines")) return { kind: "line", id };
  if (layerId === "nodes" || layerId === "load" || layerId === "load-2d") return { kind: "node", id };
  return null;
}
