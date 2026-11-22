/**
 * Map clicks: a single click selects, a double click on a line cuts it and on a substation takes it out of service. Pure, so it can be tested without a map.
 *
 * The two basemaps deliver a double click differently (see baseMap.ts):
 * - Mapbox (`MapboxOverlay`): three callbacks, `click` (tapCount 1), `click` (tapCount 1), then the DOM `dblclick`
 *   forwarded as a `click` with tapCount 2.
 * - Offline `Deck` with double-click zoom off: two callbacks, tapCount 1 then tapCount 2, each as soon as it happens.
 * Either way the first callback selects at once and exactly one of the later ones cuts.
 */

export type Pick = { kind: "line" | "node"; id: string };
export type ClickAction = { type: "select"; target: Pick } | { type: "cut"; id: string; kind: "line" | "node" } | { type: "clear" } | { type: "none" };
/** The last line or substation click: which one, when (ms), whether it cut, and which line the click before it hit. */
export interface ClickMemory { id: string | null; at: number; cut: boolean; prevId: string | null }

/** Two clicks on the same line closer than this count as a double click, even without tapCount 2 (touch on Mapbox). */
export const DOUBLE_CLICK_MS = 400;
/** A tapCount 2 callback this soon after the previous one is Mapbox's dblclick trailing the same physical click. */
const TRAILER_MS = 50;
export const NO_CLICK: ClickMemory = { id: null, at: -Infinity, cut: false, prevId: null };

export function interpretClick(target: Pick | null, tapCount: number, at: number, memory: ClickMemory): { action: ClickAction; memory: ClickMemory } {
  if (!target) return { action: { type: "clear" }, memory: NO_CLICK };
  const id = target.id;
  const none = { action: { type: "none" } as const, memory };
  const cut = { action: { type: "cut", id, kind: target.kind } as const, memory: { id, at, cut: true, prevId: memory.id } };
  if (tapCount >= 2 && at - memory.at < TRAILER_MS) {
    // Mapbox: the click itself was already handled; cut only if both physical clicks hit this line and none has cut yet.
    return !memory.cut && memory.id === id && memory.prevId === id ? cut : none;
  }
  const double = memory.id === id && (tapCount >= 2 || at - memory.at <= DOUBLE_CLICK_MS);
  if (double && memory.cut && at - memory.at <= DOUBLE_CLICK_MS) return none; // a third tap of the same gesture
  if (double) return cut;
  return { action: { type: "select", target }, memory: { id, at, cut: false, prevId: memory.id } };
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
