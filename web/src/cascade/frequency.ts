import type { Event, Timeline } from "./types";

export const CURVE_COLORS = ["#7dd3fc", "#fbbf24", "#a78bfa", "#34d399", "#f472b6", "#fb923c"];
export const NOMINAL_HZ = 50;
export const BLACKOUT_LOW_HZ = 47.5;
export const BLACKOUT_HIGH_HZ = 52;
const HORIZON_S = 20; // each island is simulated for 20 s; a shorter curve means it collapsed

type Island = { buses: number; genMw: number; loadMw: number };

export interface CurveInfo {
  key: string;
  letter: string;
  color: string;
  points: [number, number][];
  start: number;
  end: number;
  minHz: number;
  maxHz: number;
  finalHz: number;
  collapsed: boolean;
  /** Present when the engine tagged the island, or when the order of the events lets us pair it safely. */
  island?: Island;
  /** True for the flat line drawn when no island lost its balance. */
  wholeGrid?: boolean;
}

const formedEvents = (events: Event[]) => events.filter((e) => e.type === "island_formed");
const toIsland = (e: Event): Island => ({ buses: Number(e.params.buses), genMw: Number(e.params.gen_mw), loadMw: Number(e.params.load_mw) });

/** Why: the chart must say which island each line is. The curve alone tells the outcome; the island event tells its size and balance. */
export function describeCurves(curves: Timeline["frequency_hz"], events: Event[]): CurveInfo[] {
  const islandOf = taggedIslands(events) ?? inferredIslands(curves, events);
  return Object.entries(curves)
    .sort(([a], [b]) => Number(a.slice(1)) - Number(b.slice(1)))
    .map(([key, points], i) => {
      const values = points.map((p) => p[1]);
      const start = points[0][0];
      const end = points[points.length - 1][0];
      return {
        key, letter: String.fromCharCode(65 + i), color: CURVE_COLORS[i % CURVE_COLORS.length], points, start, end,
        minHz: Math.min(...values), maxHz: Math.max(...values), finalHz: values[values.length - 1], collapsed: end - start < HORIZON_S - 0.5, island: islandOf.get(key),
      };
    });
}

/** No island lost its balance (or the grid was not split): the frequency of the whole grid stays at 50 Hz. */
export function wholeGridCurve(events: Event[]): CurveInfo {
  const first = formedEvents(events)[0];
  const points: [number, number][] = [[0, NOMINAL_HZ], [HORIZON_S, NOMINAL_HZ]];
  return {
    key: "grid", letter: "", color: CURVE_COLORS[0], points, start: 0, end: HORIZON_S, minHz: NOMINAL_HZ, maxHz: NOMINAL_HZ, finalHz: NOMINAL_HZ,
    collapsed: false, island: first ? toIsland(first) : undefined, wholeGrid: true,
  };
}

/** Newer engine: each simulated island carries the key of its curve. */
function taggedIslands(events: Event[]): Map<string, Island> | null {
  const tagged = formedEvents(events).filter((e) => typeof e.params.curve === "string");
  return tagged.length ? new Map(tagged.map((e) => [String(e.params.curve), toIsland(e)])) : null;
}

/**
 * Older cache without tags: the engine simulates islands in the order it announces them, but skips balanced or empty ones.
 * Pair them in order, and trust the pairing only if every pair agrees with its curve (same start time, same direction).
 * Why: a wrong island size in the legend is worse than none.
 */
function inferredIslands(curves: Timeline["frequency_hz"], events: Event[]): Map<string, Island> {
  const keys = Object.keys(curves).sort((a, b) => Number(a.slice(1)) - Number(b.slice(1)));
  const candidates = formedEvents(events).filter(
    (e) => Math.abs(Number(e.params.gen_mw) - Number(e.params.load_mw)) >= 1 && Number(e.params.gen_mw) >= 1 && Number(e.params.load_mw) >= 1,
  );
  if (candidates.length !== keys.length) return new Map();
  const agrees = candidates.every((e, i) => {
    const values = curves[keys[i]].map((p) => p[1]);
    const deficit = Number(e.params.load_mw) > Number(e.params.gen_mw);
    return Math.abs(e.t - curves[keys[i]][0][0]) < 0.05 && (deficit ? Math.min(...values) < NOMINAL_HZ : Math.max(...values) > NOMINAL_HZ);
  });
  return agrees ? new Map(keys.map((k, i) => [k, toIsland(candidates[i])])) : new Map();
}

const hz = (n: number) => n.toLocaleString("es-CL", { minimumFractionDigits: 1, maximumFractionDigits: 2 });

/** One sentence per island for the legend. */
export function describeOutcome(c: CurveInfo): string {
  if (c.wholeGrid) return "50 Hz estables: generación y demanda están equilibradas";
  if (c.collapsed) {
    const low = c.minHz < NOMINAL_HZ - (c.maxHz - NOMINAL_HZ);
    return `${low ? "cae hasta el límite de 47,5 Hz" : "sube sobre el límite de 52 Hz"} y se apaga a los ${hz(c.end)} s`;
  }
  const settles = (peak: number) => (Math.abs(peak - c.finalHz) < 0.02 ? "y ahí se queda" : `y se estabiliza en ${hz(c.finalHz)} Hz`);
  if (c.minHz < NOMINAL_HZ - 0.1) return `cae hasta ${hz(c.minHz)} Hz ${settles(c.minHz)}`;
  if (c.maxHz > NOMINAL_HZ + 0.1) return `sube hasta ${hz(c.maxHz)} Hz ${settles(c.maxHz)}`;
  return "se mantiene en 50 Hz";
}

export function describeBalance(c: CurveInfo): string {
  if (!c.island) return "";
  const gap = Math.round(c.island.genMw - c.island.loadMw);
  if (c.wholeGrid) return `${c.island.buses} subestaciones conectadas, ${Math.round(c.island.genMw).toLocaleString("es-CL")} MW de generación y de demanda`;
  const side = gap < 0 ? `le faltan ${Math.abs(gap).toLocaleString("es-CL")} MW` : `le sobran ${gap.toLocaleString("es-CL")} MW`;
  return `${c.island.buses} subestaciones, ${side}`;
}
