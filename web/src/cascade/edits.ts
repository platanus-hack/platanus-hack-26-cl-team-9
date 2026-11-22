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
