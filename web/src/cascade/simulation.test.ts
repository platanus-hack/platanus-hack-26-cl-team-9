import { describe, expect, it } from "vitest";
import { darkAt, frequencyAt, groupEvents, impactAt, lineStateAt, markerLabel, sample, withstandsAt } from "./simulation";
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

  it("groups close events into one marker", () => {
    // 20 s on a 290 px track: 0, 1.0 and 1.5 s fall within 22 px and share a marker; the last one stays inside the track.
    const m = groupEvents(timeline.events, 20, 290);
    expect(m.map(markerLabel)).toEqual(["1–3", "4", "5"]);
    expect(m[m.length - 1].left + m[m.length - 1].width).toBeLessThanOrEqual(290);
    for (let i = 1; i < m.length; i++) expect(m[i].left).toBeGreaterThanOrEqual(m[i - 1].left + m[i - 1].width);
    expect(markerLabel({ first: 5, last: 8 })).toBe("5–8");
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
