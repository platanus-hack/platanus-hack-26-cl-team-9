import type { BusState, Event, Frame, Network, Timeline } from "./types";

/**
 * Continuous-time reading of a precomputed cascade (Design v5 timeline). The engine stores one frame per network stage
 * and events with their own times; these helpers answer "what does the system look like at second t".
 */

export const BLACKOUT_HZ = 47.5;

/** Last frame that has started at time t. */
export function frameIndexAt(tl: Timeline, t: number): number {
  let k = 0;
  for (let i = 0; i < tl.frames.length; i++) if (tl.frames[i].t <= t + 1e-9) k = i;
  return k;
}

/**
 * Buses without power at time t. A frame stores the dark set at the end of its stage, but the island only goes dark
 * when its blackout event fires (it can be seconds later, after the frequency falls), so new dark buses wait for it.
 */
export function darkAt(tl: Timeline, t: number): Set<string> {
  const k = frameIndexAt(tl, t);
  const prev = new Set(k > 0 ? tl.frames[k - 1].dark : []);
  const frame = tl.frames[k];
  const end = tl.frames[k + 1]?.t ?? Infinity;
  const blackouts = tl.events.filter((e) => e.type === "island_blackout" && e.t >= frame.t - 1e-9 && e.t < end);
  const fires = blackouts.length ? Math.min(...blackouts.map((e) => e.t)) : frame.t;
  return t + 1e-9 >= fires ? new Set(frame.dark) : prev;
}

export interface Impact { people: number; lostLoadMw: number; lostGenMw: number; share: number }

/**
 * People without supply, lost load and lost generation at time t. Dark buses count whole; load shed in islands that
 * survive is not stored per bus, so it is spread over time by the MW shed so far. At the end the values equal the
 * engine summary.
 */
export function impactAt(tl: Timeline, buses: Record<string, BusState>, t: number): Impact {
  const totalPeople = Object.values(buses).reduce((s, b) => s + b.people, 0);
  const sum = (ids: Iterable<string>, f: (b: BusState) => number) => { let s = 0; for (const id of ids) { const b = buses[id]; if (b && b.load_mw > 0) s += f(b); } return s; };
  const sumGen = (ids: Iterable<string>) => { let s = 0; for (const id of ids) s += buses[id]?.gen_mw ?? 0; return s; };
  const dark = darkAt(tl, t);
  const finalDark = tl.frames[tl.frames.length - 1]?.dark ?? [];
  const summary = tl.summary;
  const residualPeople = Math.max(0, summary.people_without_power - sum(finalDark, (b) => b.people));
  const residualMw = Math.max(0, summary.load_shed_mw - sum(finalDark, (b) => b.load_mw));
  const sheds = tl.events.filter((e) => e.type === "load_shed");
  const shedTotal = sheds.reduce((s, e) => s + Number(e.params.mw ?? 0), 0);
  const shedNow = sheds.filter((e) => e.t <= t + 1e-9).reduce((s, e) => s + Number(e.params.mw ?? 0), 0);
  if (t + 1e-9 >= lastEventTime(tl) && tl.events.length > 1) {
    return { people: summary.people_without_power, lostLoadMw: summary.load_shed_mw, lostGenMw: Math.round(sumGen(dark)), share: totalPeople > 0 ? summary.people_without_power / totalPeople : 0 };
  }
  const progress = shedTotal > 0 ? shedNow / shedTotal : 0;
  // Load shed before its island collapses is already lost: count it at the system's people per MW, capped by the summary.
  const peoplePerMw = summary.load_total_mw > 0 ? totalPeople / summary.load_total_mw : 0;
  const people = Math.round(Math.min(summary.people_without_power, Math.max(sum(dark, (b) => b.people) + residualPeople * progress, shedNow * peoplePerMw)));
  const lostLoadMw = Math.round(Math.min(summary.load_shed_mw, Math.max(sum(dark, (b) => b.load_mw) + residualMw * progress, shedNow)));
  return { people, lostLoadMw, lostGenMw: Math.round(sumGen(dark)), share: totalPeople > 0 ? people / totalPeople : 0 };
}

export function lastEventTime(tl: Timeline): number {
  return tl.events.length ? tl.events[tl.events.length - 1].t : 0;
}

export interface IslandFrequency { id: string; name: string; hz: number | null; minHz: number; started: boolean; collapsed: boolean }

/** Frequency of each island at time t (linear between samples). `hz` is null before the island exists. */
export function frequencyAt(tl: Timeline, t: number): IslandFrequency[] {
  return Object.entries(tl.frequency_hz).map(([id, curve], i) => {
    const minHz = Math.min(...curve.map((p) => p[1]));
    const started = curve.length > 0 && t + 1e-9 >= curve[0][0];
    const lastT = curve[curve.length - 1]?.[0] ?? 0;
    // The curve of an island that blacks out stops at its blackout event; the sampled minimum can sit a hair above 47,5 Hz.
    const endsInBlackout = tl.events.some((e) => e.type === "island_blackout" && Math.abs(e.t - lastT) < 0.3);
    const collapsed = (endsInBlackout || minHz < BLACKOUT_HZ) && t + 1e-9 >= lastT && lastT < tl.duration_s - 0.5;
    return { id, name: `Isla ${i + 1}`, hz: started ? sample(curve, t) : null, minHz, started, collapsed };
  });
}

export function sample(curve: [number, number][], t: number): number {
  if (!curve.length) return 50;
  if (t <= curve[0][0]) return curve[0][1];
  for (let i = 1; i < curve.length; i++) {
    const [t1, f1] = curve[i];
    if (t <= t1) {
      const [t0, f0] = curve[i - 1];
      return t1 === t0 ? f1 : f0 + ((f1 - f0) * (t - t0)) / (t1 - t0);
    }
  }
  return curve[curve.length - 1][1];
}

/** Events whose markers would overlap on the track share one marker ("1·2"). `left` is the marker's x on the track. */
export interface Marker { first: number; last: number; t: number; events: Event[]; left: number; width: number }

export const markerLabel = (m: Pick<Marker, "first" | "last">) => (m.first === m.last ? `${m.first}` : m.last === m.first + 1 ? `${m.first}·${m.last}` : `${m.first}–${m.last}`);
const markerWidth = (m: Pick<Marker, "first" | "last">) => Math.max(20, 10 + 6.6 * markerLabel(m).length);
const MARKER_SPACE_PX = 3;

export function groupEvents(events: Event[], duration: number, trackWidth: number): Marker[] {
  const x = (t: number) => (duration > 0 ? (Math.min(t, duration) / duration) * trackWidth : 0);
  const out: Marker[] = [];
  events.forEach((e, i) => {
    const g = out[out.length - 1];
    const n = i + 1;
    if (g && x(e.t) - 10 < g.left + markerWidth({ first: g.first, last: n }) + MARKER_SPACE_PX) {
      g.last = n; g.events.push(e); g.width = markerWidth(g);
    } else {
      const left = Math.max(g ? g.left + g.width + MARKER_SPACE_PX : 0, x(e.t) - 10);
      out.push({ first: n, last: n, t: e.t, events: [e], left, width: 20 });
    }
  });
  // Keep the last markers inside the track: shift left, never overlapping the one before.
  let limit = trackWidth;
  for (let i = out.length - 1; i >= 0; i--) {
    const m = out[i];
    m.left = Math.max(0, Math.min(m.left, limit - m.width));
    limit = m.left - MARKER_SPACE_PX;
  }
  return out;
}


/** Where an event happens on the map, when it has a place: the cut or opened line, the shed zone, or the dark area. */
export function eventLocation(e: Event, tl: Timeline, network: Network): [number, number] | null {
  const node = (id: string) => network.nodes.find((n) => n.id === id);
  const centroid = (ids: string[]): [number, number] | null => {
    const pts = ids.map(node).filter((n) => !!n);
    if (!pts.length) return null;
    return [pts.reduce((s, n) => s + n!.lon, 0) / pts.length, pts.reduce((s, n) => s + n!.lat, 0) / pts.length];
  };
  if (e.type === "line_cut" || e.type === "line_overload_open") {
    const ends = e.ids.flatMap((id) => { const l = network.lines.find((x) => x.id === id); return l ? [l.a, l.b] : []; });
    return centroid(ends);
  }
  if (e.type === "load_shed") return centroid(network.nodes.filter((n) => n.zone === e.params.zone).map((n) => n.id));
  if (e.type === "island_blackout") {
    const before = darkAt(tl, e.t - 1e-3);
    return centroid([...darkAt(tl, e.t)].filter((id) => !before.has(id)));
  }
  return null;
}

/** Frame edges, with the dark set of time t (not the end of the stage). */
export function frameAt(tl: Timeline, t: number): Frame {
  const f = tl.frames[frameIndexAt(tl, t)];
  return { ...f, dark: [...darkAt(tl, t)] };
}
