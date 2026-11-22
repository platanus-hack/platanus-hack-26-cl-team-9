import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { darkAt, frequencyAt, groupEvents, impactAt, lineStateAt, MARKER_GAP_PX, markerLabel, MIN_GAP_VIEW_S, sample, TAIL_SHARE, timeWarp, withstandsAt } from "./simulation";
import type { BusState, Event, NetLine, Timeline } from "./types";

const ev = (t: number, type: string, params: Event["params"] = {}): Event => ({ t, type, ids: [], text_key: type, params });

const timeline: Timeline = {
  scenario: "p", label: "p", failed_elements: ["R1"], truncated: false, duration_s: 20,
  events: [ev(0, "line_cut"), ev(1, "island_formed"), ev(1.5, "load_shed", { mw: 10 }), ev(4, "island_blackout"), ev(20, "island_stable")],
  frames: [
    { t: 0, edges: {}, dark: [], islands: [] },
    { t: 1, edges: {}, dark: ["B1"], islands: [] },
  ],
  frequency_hz: { I1: [[1, 50], [2, 49], [4, 47]], I2: [[1, 50], [3, 50.5]] },
  summary: { people_without_power: 130, load_shed_mw: 110, load_total_mw: 300, stages: 1, lines_opened: ["R1"], dark_buses: 1, islands: [] },
  assumptions: [],
};
const buses: Record<string, BusState> = { B1: { gen_mw: 40, load_mw: 100, people: 100 }, B2: { gen_mw: 260, load_mw: 200, people: 200 } };

describe("cascade at time t", () => {
  it("keeps a new dark island lit until its blackout event fires", () => {
    expect(darkAt(timeline, 2).size).toBe(0);
    expect([...darkAt(timeline, 4)]).toEqual(["B1"]);
  });

  it("ends at the engine summary and spreads partial shedding over time", () => {
    expect(impactAt(timeline, buses, 0).people).toBe(0);
    expect(impactAt(timeline, buses, 2)).toMatchObject({ people: 30, lostLoadMw: 10 });
    expect(impactAt(timeline, buses, 20)).toMatchObject({ people: 130, lostLoadMw: 110, lostGenMw: 40 });
  });

  it("samples island frequency linearly and flags a collapse", () => {
    expect(sample([[0, 50], [2, 48]], 1)).toBeCloseTo(49);
    const [i1, i2] = frequencyAt(timeline, 5);
    expect(i1).toMatchObject({ hz: 47, collapsed: true });
    expect(i2).toMatchObject({ hz: 50.5, collapsed: false });
    expect(frequencyAt(timeline, 0.5)[0].hz).toBeNull();
  });

  it("groups only same-instant events and keeps every marker inside the track", () => {
    const m = groupEvents(timeline.events, timeWarp(timeline, 290), 290);
    // the shed at 1.5 s joins the new island at 1.0 s; the cut, the island and the blackout keep their own markers
    expect(m.map(markerLabel)).toEqual(["1", "2·3", "4", "5"]);
    expect(m[m.length - 1].left + m[m.length - 1].width).toBeLessThanOrEqual(290);
    for (let i = 1; i < m.length; i++) expect(m[i].left).toBeGreaterThanOrEqual(m[i - 1].left + m[i - 1].width);
    expect(markerLabel({ first: 5, last: 8 })).toBe("5–8");
  });
});

// A real 4-stage cascade with a re-split island (docs/engine.md "Hand-checked cuts"): openings at 1.0, 2.0, 7.59 and 8.59 s,
// a 45-bus blackout at 6.59 s and a 1-bus blackout at 8.59 s.
const r026: Timeline = JSON.parse(readFileSync("public/cache/nov2026-1300/R026.json", "utf8"));

describe("non-linear track scale", () => {
  const warp = timeWarp(r026, 290);
  const x = (t: number) => (warp.toView(t) / warp.viewDuration) * 290;

  it("is increasing and goes back and forth", () => {
    let prev = -1;
    for (let t = 0; t <= r026.duration_s; t += 0.05) {
      const v = warp.toView(t);
      expect(v).toBeGreaterThan(prev);
      expect(warp.toSim(v)).toBeCloseTo(t, 6);
      prev = v;
    }
    expect(warp.toView(r026.duration_s)).toBeCloseTo(warp.viewDuration, 9);
  });

  it("keeps every opening and blackout at least a marker apart and squeezes the tail", () => {
    const keys = [...new Set(r026.events.filter((e) => ["line_cut", "line_overload_open", "island_blackout"].includes(e.type)).map((e) => e.t))].sort((a, b) => a - b);
    for (let i = 1; i < keys.length; i++) {
      expect(x(keys[i]) - x(keys[i - 1])).toBeGreaterThanOrEqual(MARKER_GAP_PX - 1e-6);
      expect(warp.toView(keys[i]) - warp.toView(keys[i - 1])).toBeGreaterThanOrEqual(MIN_GAP_VIEW_S - 1e-9);
    }
    const lastEffect = Math.max(...r026.events.filter((e) => e.type !== "island_stable").map((e) => e.t));
    expect(290 - x(lastEffect)).toBeLessThanOrEqual(290 * TAIL_SHARE + 1e-6);
    // the 20 s transient tail no longer fills most of the track
    expect(warp.viewDuration).toBeLessThan(r026.duration_s);
  });

  it("gives each stage and each blackout its own marker", () => {
    const m = groupEvents(r026.events, warp, 290);
    for (const e of r026.events.filter((ev) => ev.type === "line_overload_open" || ev.type === "island_blackout")) {
      const own = m.find((g) => g.events.includes(e))!;
      // a marker never holds two different instants that open or darken something
      expect(new Set(own.events.filter((ev) => ev.type !== "load_shed" && ev.type !== "island_stable").map((ev) => ev.t)).size).toBe(1);
    }
    expect(m.length).toBeGreaterThanOrEqual(7);
  });

  it("numbers markers over the same event list as the history", () => {
    const m = groupEvents(r026.events, warp, 290);
    expect(m[0].first).toBe(1);
    for (let i = 1; i < m.length; i++) expect(m[i].first).toBe(m[i - 1].last + 1);
    expect(m[m.length - 1].last).toBe(r026.events.length);
    m.forEach((g) => g.events.forEach((e, k) => expect(r026.events[g.first - 1 + k]).toBe(e)));
  });

  it("is the identity without a timeline", () => {
    const id = timeWarp(null, 290);
    expect(id.toView(3)).toBe(3);
    expect(id.toSim(3)).toBe(3);
  });
});

describe("dark substations at the blackout's own time", () => {
  const twoBlackouts: Timeline = {
    ...timeline,
    events: [ev(0, "line_cut"), ev(1, "island_formed"), { ...ev(1.4, "island_blackout"), ids: ["B1"] }, { ...ev(3.2, "island_blackout"), ids: ["B2", "B3"] }],
    frames: [{ t: 0, edges: {}, dark: [], islands: [] }, { t: 1, edges: {}, dark: ["B1", "B2", "B3", "B9"], islands: [] }],
  };

  it("darkens each island of one stage when its own blackout fires", () => {
    expect([...darkAt(twoBlackouts, 1.2)]).toEqual(["B9"]); // B9: dark in the frame but in no blackout (out of service)
    expect([...darkAt(twoBlackouts, 1.4)].sort()).toEqual(["B1", "B9"]);
    expect([...darkAt(twoBlackouts, 3.2)].sort()).toEqual(["B1", "B2", "B3", "B9"]);
  });

});

describe("line state", () => {
  const line: NetLine = { id: "R1", a: "B1", b: "B2", kv: 220, capacity_mw: 100, x_pu: 0.1, map_edges: [], branches: ["x"] };
  const frame = (edge: { flow_mw: number; status: "ok" | "overload" | "open"; loading: number }, dark: string[] = []) => ({ t: 0, edges: { R1: edge }, dark, islands: [] });

  it("reads flow direction from the sign and flags overloads", () => {
    expect(lineStateAt(line, frame({ flow_mw: -80, status: "ok", loading: 0.8 }))).toEqual({ status: "en servicio", flowMw: 80, loading: 0.8, from: "B2", to: "B1", atLimit: false });
    expect(lineStateAt(line, frame({ flow_mw: 130, status: "overload", loading: 1.3 })).status).toBe("sobrecargada");
    // The engine flags a line exactly at its limit as "overload"; it is at its limit, not over it.
    expect(lineStateAt(line, frame({ flow_mw: 100, status: "overload", loading: 1 }))).toMatchObject({ status: "en servicio", atLimit: true });
  });

  it("puts out of service before dead, and dead before overload", () => {
    expect(lineStateAt(line, frame({ flow_mw: 0, status: "open", loading: 0 }, ["B1", "B2"])).status).toBe("fuera de servicio");
    expect(lineStateAt(line, frame({ flow_mw: 0, status: "ok", loading: 0 }, ["B1", "B2"])).status).toBe("sin tensión");
    expect(lineStateAt(line, frame({ flow_mw: 0, status: "ok", loading: 0 }, ["B1"])).status).toBe("en servicio");
  });
});

describe("a cut the system withstands", () => {
  const calm: Timeline = { ...timeline, summary: { ...timeline.summary, people_without_power: 0, load_shed_mw: 0 } };
  it("is reported only once the last event has played", () => {
    expect(withstandsAt(calm, 5)).toBe(false);
    expect(withstandsAt(calm, 20)).toBe(true);
    expect(withstandsAt(timeline, 20)).toBe(false);
  });
});
