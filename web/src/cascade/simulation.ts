import type { BusState, Event, Frame, NetLine, Network, Timeline } from "./types";

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
 * Buses without power at time t. Each `island_blackout` lists its buses (`ids`), so they go dark at the event's own
 * time, also when several islands of one stage go dark at different times. Buses dark in the last frame that no
 * blackout lists (a substation taken out of service) are dark from t = 0. Timelines whose blackouts carry no ids
 * (older caches and sessions) fall back to the frame logic: a frame's dark set appears at its first blackout.
 */
export function darkAt(tl: Timeline, t: number): Set<string> {
  const blackouts = tl.events.filter((e) => e.type === "island_blackout");
  if (blackouts.length === 0 || blackouts.every((e) => e.ids.length > 0)) {
    const listed = new Set(blackouts.flatMap((e) => e.ids));
    const out = new Set((tl.frames[tl.frames.length - 1]?.dark ?? []).filter((id) => !listed.has(id)));
    for (const e of blackouts) if (e.t <= t + 1e-9) for (const id of e.ids) out.add(id);
    return out;
  }
  return frameDarkAt(tl, t);
}

function frameDarkAt(tl: Timeline, t: number): Set<string> {
  const k = frameIndexAt(tl, t);
  const prev = new Set(k > 0 ? tl.frames[k - 1].dark : []);
  const frame = tl.frames[k];
  const end = tl.frames[k + 1]?.t ?? Infinity;
  const blackouts = tl.events.filter((e) => e.type === "island_blackout" && e.t >= frame.t - 1e-9 && e.t < end);
  const fires = blackouts.length ? Math.min(...blackouts.map((e) => e.t)) : frame.t;
  return t + 1e-9 >= fires ? new Set(frame.dark) : prev;
}

/**
 * Non-linear time scale of the track (issue #90). Simulated seconds `t` map to view seconds `v`, piecewise linear and
 * increasing. The nodes are the instants that cut, open or darken something (and the last load shed). Every gap between
 * two nodes gets at least `MIN_GAP_VIEW_S` and at least the view length that keeps their markers `MARKER_GAP_PX` apart on
 * a track `trackWidth` wide, so each stage and each blackout has its own marker. Long gaps keep their real length, and the tail after the last
 * event with an effect is squeezed to about `TAIL_SHARE` of the track. Playback advances in view time, so the
 * simulation slows near each failure and runs fast through the tail; the clock still shows simulated seconds.
 */
export interface TimeWarp { toView(t: number): number; toSim(v: number): number; viewDuration: number }
export const MARKER_GAP_PX = 30;
export const TAIL_SHARE = 0.15;
const MIN_TAIL_VIEW_S = 1.5;
/** Every gap between two nodes lasts at least this long on the track, so at 1x each failure gets 1.5 s on screen. */
export const MIN_GAP_VIEW_S = 1.5;
const FALLBACK_GAP_VIEW_S = 1.5;
const KEY_EVENTS = new Set(["line_cut", "line_overload_open", "island_formed", "island_blackout"]);

export function timeWarp(tl: Timeline | null, trackWidth: number): TimeWarp {
  const duration = tl?.duration_s ?? 0;
  if (!tl || duration <= 0) return { toView: (t) => t, toSim: (v) => v, viewDuration: duration };
  const nodes = [...new Set([0, ...tl.events.filter((e) => KEY_EVENTS.has(e.type)).map((e) => e.t)])].sort((a, b) => a - b);
  const sheds = tl.events.filter((e) => e.type === "load_shed").map((e) => e.t);
  const lastShed = sheds.length ? Math.max(...sheds) : 0;
  if (lastShed > nodes[nodes.length - 1] + 1e-9) nodes.push(lastShed);
  const end = Math.min(nodes[nodes.length - 1], duration);
  const gaps = nodes.slice(1).map((n, i) => n - nodes[i]);
  const simTail = duration - end;
  const tailOf = (body: number) => Math.min(simTail, Math.max((body * TAIL_SHARE) / (1 - TAIL_SHARE), MIN_TAIL_VIEW_S));
  const bodyOf = (m: number) => gaps.reduce((s, g) => s + Math.max(g, m), 0);
  // Smallest view gap m with m / (body(m) + tail) x trackWidth >= MARKER_GAP_PX. When too many nodes share the track for
  // that to exist (9 or more nodes on 290 px, 5 of the 1,848 cached cuts), each gap gets at least 1.5 s and the
  // markers are packed side by side by `groupEvents`.
  const k = MARKER_GAP_PX / trackWidth;
  let m = 0;
  if (gaps.length && (k * gaps.length) / (1 - TAIL_SHARE) < 0.98) {
    m = MIN_GAP_VIEW_S;
    for (let i = 0; i < 100; i++) m = Math.max(MIN_GAP_VIEW_S, k * (bodyOf(m) + tailOf(bodyOf(m))));
  } else if (gaps.length) {
    m = FALLBACK_GAP_VIEW_S;
  }
  const sim = nodes.filter((n) => n <= end);
  const view = [0];
  for (let i = 1; i < sim.length; i++) view.push(view[i - 1] + Math.max(sim[i] - sim[i - 1], m));
  const bodyView = view[view.length - 1];
  if (simTail > 1e-9) { sim.push(duration); view.push(bodyView + tailOf(bodyView)); }
  return {
    toView: (t) => interp(sim, view, t),
    toSim: (v) => interp(view, sim, v),
    viewDuration: view[view.length - 1],
  };
}

/** Piecewise-linear interpolation of increasing knots, clamped at both ends. */
function interp(xs: number[], ys: number[], x: number): number {
  if (xs.length === 1 || x <= xs[0]) return ys[0] + (xs.length === 1 ? x - xs[0] : 0);
  for (let i = 1; i < xs.length; i++) {
    if (x <= xs[i]) return xs[i] === xs[i - 1] ? ys[i] : ys[i - 1] + ((ys[i] - ys[i - 1]) * (x - xs[i - 1])) / (xs[i] - xs[i - 1]);
  }
  return ys[ys.length - 1];
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
  if (t + 1e-9 >= lastEventTime(tl) && tl.events.length > 0) {
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

/**
 * Track markers, one per event or per group of events. Events at the same instant always share a marker. A cut, an
 * opening, a new island or a blackout never joins an earlier marker otherwise, so each cascade stage and each blackout
 * keeps its own; load shed and stable-island events join the marker before them when they would overlap it (EDAC steps
 * of one island can share a marker). `left` is the marker's x on the track, from the warped time.
 */
export interface Marker { first: number; last: number; t: number; events: Event[]; left: number; width: number }

export const markerLabel = (m: Pick<Marker, "first" | "last">) => (m.first === m.last ? `${m.first}` : m.last === m.first + 1 ? `${m.first}·${m.last}` : `${m.first}–${m.last}`);
const markerWidth = (m: Pick<Marker, "first" | "last">) => Math.max(20, 10 + 6.6 * markerLabel(m).length);
const MARKER_SPACE_PX = 3;

export function groupEvents(events: Event[], warp: TimeWarp, trackWidth: number): Marker[] {
  const x = (t: number) => (warp.viewDuration > 0 ? (Math.min(warp.toView(t), warp.viewDuration) / warp.viewDuration) * trackWidth : 0);
  const out: Marker[] = [];
  events.forEach((e, i) => {
    const g = out[out.length - 1];
    const n = i + 1;
    const sameInstant = g && Math.abs(e.t - g.events[g.events.length - 1].t) < 1e-6;
    const overlaps = g && x(e.t) - 10 < g.left + markerWidth({ first: g.first, last: n }) + MARKER_SPACE_PX;
    if (g && (sameInstant || (overlaps && !KEY_EVENTS.has(e.type)))) {
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

export type LineStatus = "en servicio" | "sobrecargada" | "fuera de servicio" | "sin tensión";
/**
 * A line at the current frame, as the engine computed it: flow from `from` to `to` (bus ids), loading as a share of
 * capacity. The engine marks lines that sit exactly at their limit in the base case as "overload" (loading 1.0); the
 * map draws them as 75-100 %, so here only loading above 100 % counts as overloaded and the limit is `atLimit`.
 */
export interface LineState { status: LineStatus; flowMw: number; loading: number; from: string; to: string; atLimit: boolean }

export function lineStateAt(line: NetLine, frame: Frame | undefined): LineState {
  const e = frame?.edges[line.id];
  const dark = new Set(frame?.dark ?? []);
  const flow = e?.flow_mw ?? 0;
  const [from, to] = flow >= 0 ? [line.a, line.b] : [line.b, line.a];
  const status: LineStatus = e?.status === "open" ? "fuera de servicio" : dark.has(line.a) && dark.has(line.b) ? "sin tensión"
    : e && e.loading > 1 + 1e-6 ? "sobrecargada" : "en servicio";
  const loading = e?.status === "open" ? 0 : e?.loading ?? 0;
  return { status, flowMw: e?.status === "open" ? 0 : Math.abs(flow), loading, from, to, atLimit: status === "en servicio" && loading >= 0.995 };
}

/** True once the cascade has played out (last event reached) and the engine found nobody without supply and no lost load. */
export function withstandsAt(tl: Timeline, t: number): boolean {
  return t + 1e-9 >= lastEventTime(tl) && tl.summary.people_without_power === 0 && tl.summary.load_shed_mw === 0;
}
