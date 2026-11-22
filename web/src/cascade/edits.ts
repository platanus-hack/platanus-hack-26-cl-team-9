/**
 * One change of a prepared scenario (docs/stress.md): the filters pick the elements, `factor` multiplies each one and
 * `add` adds one total. The card of a component writes a change for that component alone; the assistant may write
 * changes by filters (zones, technologies, comunas).
 */
export interface StressChange {
  target: "population" | "demand" | "generation" | "lines" | "substation";
  buses?: string[]; zones?: string[]; areas?: string[]; comunas?: string[]; tech?: string[]; lines?: string[]; kv?: number[];
  /** Places as the person named them; the server resolves each to one substation (docs/stress.md section 3). */
  places?: string[];
  factor?: number; add?: number; x_factor?: number;
  /** A new substation (target "substation"): built next to the one that serves `places[0]`, with its own lines. */
  name?: string; lat?: number; lon?: number; load_mw?: number; generator_mw?: number;
}
export type Target = StressChange["target"];

/** The changes the user made to the grid: lines cut, substations out of service, and the prepared scenario. */
export interface Edits { lines: string[]; buses: string[]; changes?: StressChange[] }

export const NO_EDITS: Edits = { lines: [], buses: [] };
export const changesOf = (e: Edits) => e.changes ?? [];
export const countFailures = (e: Edits) => e.lines.length + e.buses.length;
export const countEdits = (e: Edits) => countFailures(e) + changesOf(e).length;
/** Zero or one line, no substation and no prepared change: the app cache already has that cascade. */
export const fromCache = (e: Edits) => changesOf(e).length === 0 && e.buses.length === 0 && e.lines.length <= 1;

export const addLine = (e: Edits, id: string): Edits => (e.lines.includes(id) ? e : { ...e, lines: [...e.lines, id] });
export const addBus = (e: Edits, id: string): Edits => (e.buses.includes(id) ? e : { ...e, buses: [...e.buses, id] });
export const dropLine = (e: Edits, id: string): Edits => ({ ...e, lines: e.lines.filter((x) => x !== id) });
export const dropBus = (e: Edits, id: string): Edits => ({ ...e, buses: e.buses.filter((x) => x !== id) });

/** Identifies one simulation, so a timeline that arrives late is never shown under newer changes. */
export const editKey = (point: string, e: Edits) => `edit:${point}:${[...e.lines].sort()}|${[...e.buses].sort()}|${JSON.stringify(changesOf(e))}`;

/** The change a component's own card wrote: one target on that bus or line alone, by factor. */
const ownOf = (target: Target, id: string) => (c: StressChange) => {
  const ids = target === "lines" ? c.lines : c.buses;
  const others = target === "lines" ? [c.buses, c.zones, c.areas, c.kv, c.places] : [c.lines, c.zones, c.areas, c.comunas, c.tech, c.places];
  return c.target === target && ids?.length === 1 && ids[0] === id && c.factor !== undefined && others.every((x) => !x?.length);
};

/** The factor a component's card set for `target` (1 when it set none). */
export const factorOf = (e: Edits, target: Target, id: string) => changesOf(e).find(ownOf(target, id))?.factor ?? 1;

/** Sets the factor of one component in its card, replacing its own earlier one; 1 removes it. */
export function setFactor(e: Edits, target: Target, id: string, factor: number): Edits {
  const rest = changesOf(e).filter((c) => !ownOf(target, id)(c));
  if (!Number.isFinite(factor) || Math.abs(factor - 1) < 1e-9) return { ...e, changes: rest };
  const where = target === "lines" ? { lines: [id] } : { buses: [id] };
  return { ...e, changes: [...rest, { target, ...where, factor: Math.round(factor * 10000) / 10000 }] };
}

export const dropChange = (e: Edits, index: number): Edits => ({ ...e, changes: changesOf(e).filter((_, i) => i !== index) });

const STORAGE_KEY = "sub50.edits.v1";
type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/**
 * Why: a refresh or a closed tab must not lose the changes; they live in this browser only (localStorage). A reload
 * brings them back only when the URL describes them; otherwise the page offers to restore them (`startEdits`).
 */
export function saveEdits(e: Edits, store: Store | undefined = globalThis.localStorage): void {
  if (!store) return;
  if (countEdits(e) === 0) store.removeItem(STORAGE_KEY);
  else store.setItem(STORAGE_KEY, JSON.stringify(e));
}

/**
 * The changes the page opens with. The URL wins: a link's `cut` (a line, or `sub-<bus>` for a substation) is the only
 * change. Without one the page starts clean, so a bare `/` never shows a previous visitor's cut (F-14); the changes
 * saved in this browser come back as `restorable`, for a notice that offers to restore them.
 */
export function startEdits(cut: string | null, stored: Edits): { edits: Edits; restorable: Edits | null } {
  if (cut) {
    const node = cut.startsWith("sub-") ? cut.slice(4) : null;
    return { edits: node ? addBus(NO_EDITS, node) : addLine(NO_EDITS, cut), restorable: null };
  }
  return { edits: NO_EDITS, restorable: countEdits(stored) > 0 ? stored : null };
}

/** The saved changes, or none when nothing valid is stored. */
export function loadEdits(store: Store | undefined = globalThis.localStorage): Edits {
  try {
    const raw = JSON.parse(store?.getItem(STORAGE_KEY) ?? "null");
    const ids = (x: unknown) => (Array.isArray(x) ? x.filter((v): v is string => typeof v === "string") : []);
    const changes = Array.isArray(raw?.changes) ? raw.changes.filter((c: unknown) => !!c && typeof c === "object" && "target" in c) : [];
    return raw ? { lines: ids(raw.lines), buses: ids(raw.buses), ...(changes.length ? { changes } : {}) } : NO_EDITS;
  } catch {
    return NO_EDITS;
  }
}

/** The backend's bounds for a card factor (`StressChange` in docs/stress.md): 0 to 5, and over 0 for a line's capacity. */
export const MAX_FACTOR = 5;

/**
 * A factor typed in a card, or why it cannot be used. A blank or non-numeric field is an error, never 0 (A2-02:
 * `Number("")` is 0, which the backend refuses for a line). Accepts a decimal comma.
 */
export function parseFactor(text: string, target: Target): { factor: number } | { error: string } {
  const raw = text.trim().replace(",", ".");
  const f = raw === "" ? NaN : Number(raw);
  const lineBound = target === "lines";
  const range = lineBound ? "mayor que 0 y hasta 5" : "entre 0 y 5";
  if (!Number.isFinite(f) || f > MAX_FACTOR || f < 0 || (lineBound && f === 0)) return { error: `Escribe un número ${range}.` };
  return { factor: f };
}
