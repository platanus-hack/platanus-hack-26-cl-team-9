import { describe, expect, it } from "vitest";
import { areaFill, crewPosition, POSTURE_COLOR, servedBuses } from "./layers";
import type { Crew, TheaterNetwork } from "./types";

const net = {
  nodes: [
    { id: "B000", name: "A", lon: -70, lat: -20, kv: 220, zone: "norte_grande", map_nodes: [], area: "A01" },
    { id: "B001", name: "B", lon: -71, lat: -30, kv: 220, zone: "centro_sur", map_nodes: [], area: "A07" },
  ],
  lines: [], buses: { B000: { gen_mw: 0, load_mw: 100, people: 10 }, B001: { gen_mw: 0, load_mw: 50, people: 5 } },
  areas: [], corridors: [], defenses: {}, zones: [], point: "p", points: ["p"],
} as unknown as TheaterNetwork;

const crew = (over: Partial<Crew>): Crew => ({
  id: "K1", base: "A01", position: "A01", bus: "B000", lon: -70, lat: -20, task: "restore_element:A07", target: "A07",
  target_bus: "B001", arrival: 14, status: "busy", ...over,
});

describe("crewPosition", () => {
  it("moves linearly from the crew's position to the target substation", () => {
    expect(crewPosition(crew({}), net, 10, 10)).toEqual([-70, -20]);
    expect(crewPosition(crew({}), net, 12, 10)).toEqual([-70.5, -25]);
    expect(crewPosition(crew({}), net, 20, 10)).toEqual([-71, -30]);
  });

  it("stays put when free", () => {
    expect(crewPosition(crew({ status: "free", task: null, target_bus: null, arrival: null }), net, 12, undefined)).toEqual([-70, -20]);
  });
});

describe("area fill", () => {
  it("uses the posture colour and gets more opaque as observability drops", () => {
    const clear = areaFill("normal", 1), blind = areaFill("normal", 0);
    expect(clear.slice(0, 3)).toEqual(POSTURE_COLOR.normal.slice(0, 3));
    expect(blind[3]).toBeGreaterThan(clear[3]);
    expect(areaFill("segmented", 1).slice(0, 3)).toEqual(POSTURE_COLOR.segmented.slice(0, 3));
  });
});

describe("served buses", () => {
  it("replaces the plan load by the served load of the cycle", () => {
    const b = servedBuses(net, { t: 0, edges: {}, dark: [], islands: [], buses: { B000: 40 } } as never);
    expect(b.B000.load_mw).toBe(40);
    expect(b.B001.load_mw).toBe(50);
  });
});
