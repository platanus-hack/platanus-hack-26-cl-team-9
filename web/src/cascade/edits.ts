/** The changes the user made to the grid (outside a session): lines cut and substations out of service. */
export interface Edits { lines: string[]; buses: string[] }

export const NO_EDITS: Edits = { lines: [], buses: [] };
export const countEdits = (e: Edits) => e.lines.length + e.buses.length;
/** Zero or one line and no substation: the app cache already has that cascade, so no server call is needed. */
export const fromCache = (e: Edits) => e.buses.length === 0 && e.lines.length <= 1;

export const addLine = (e: Edits, id: string): Edits => (e.lines.includes(id) ? e : { ...e, lines: [...e.lines, id] });
export const addBus = (e: Edits, id: string): Edits => (e.buses.includes(id) ? e : { ...e, buses: [...e.buses, id] });
export const dropLine = (e: Edits, id: string): Edits => ({ ...e, lines: e.lines.filter((x) => x !== id) });
export const dropBus = (e: Edits, id: string): Edits => ({ ...e, buses: e.buses.filter((x) => x !== id) });

/** Identifies one simulation, so a timeline that arrives late is never shown under newer changes. */
export const editKey = (point: string, e: Edits) => `edit:${point}:${[...e.lines].sort()}|${[...e.buses].sort()}`;

const STORAGE_KEY = "sub50.edits.v1";
type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/** Why: a refresh or a closed tab must not lose the changes; they live in this browser only (localStorage). */
export function saveEdits(e: Edits, store: Store | undefined = globalThis.localStorage): void {
  if (!store) return;
  if (e.lines.length + e.buses.length === 0) store.removeItem(STORAGE_KEY);
  else store.setItem(STORAGE_KEY, JSON.stringify(e));
}

/** The saved changes, or none when nothing valid is stored. */
export function loadEdits(store: Store | undefined = globalThis.localStorage): Edits {
  try {
    const raw = JSON.parse(store?.getItem(STORAGE_KEY) ?? "null");
    const ids = (x: unknown) => (Array.isArray(x) ? x.filter((v): v is string => typeof v === "string") : []);
    return raw ? { lines: ids(raw.lines), buses: ids(raw.buses) } : NO_EDITS;
  } catch {
    return NO_EDITS;
  }
}
