import { describe, expect, it } from "vitest";
import type { Prepared } from "./gridsApi";
import { placedPoints } from "./placed";
import type { Network } from "./types";

const node = (id: string, name: string, lon: number, lat: number) => ({ id, name, lon, lat, kv: 220, zone: "NG", map_nodes: [] });
const NETWORK: Network = { nodes: [node("B010", "S/E ANTOFAGASTA", -70.4, -23.6), node("B058", "S/E CONDORES", -70.1, -20.3)], lines: [] };
const prepared = (changes: Prepared["changes"]): Prepared => ({
  point: "nov2026-1300", changes, per_capita_w: 238, totals: { people_total: 0, load_total_mw: 0, gen_total_mw: 0 },
  overloaded_lines: [], should_feed: { sources: [], by_zone: {} } as unknown as Prepared["should_feed"], assumptions: [],
});

describe("placedPoints", () => {
  it("pins a datacenter and a new plant at the substations their places resolved to", () => {
    const changes = [
      { target: "demand" as const, places: ["Antofagasta"], add: 120 },
      { target: "generation" as const, places: ["Iquique"], tech: ["solar"], add: 80 },
    ];
    const out = placedPoints(changes, prepared([
      { target: "demand", matched: 1, elements: [{ id: "B010", load_mw: [15, 135] }] },
      { target: "generation", matched: 1, tech: ["solar"], new_plant: true, elements: [{ id: "B058", gen_mw: [0, 80] }] },
    ]), NETWORK);
    expect(out.map((p) => [p.name, p.label, p.kind])).toEqual([
      ["S/E ANTOFAGASTA", "+120 MW de demanda", "load"],
      ["S/E CONDORES", "+80 MW solar", "gen"],
    ]);
    expect(out[0]).toMatchObject({ lon: -70.4, lat: -23.6, color: null }); // a load is a ring
    expect(out[1].color).toBe("rgb(255, 196, 0)"); // solar, as on the map
  });

  it("draws no pin for factors, cuts in demand or adds spread over a whole zone", () => {
    const wide = Array.from({ length: 6 }, (_, k) => ({ id: "B010", load_mw: [k, k + 1] as [number, number] }));
    const changes = [
      { target: "generation" as const, tech: ["hidro"], factor: 0.5 },
      { target: "demand" as const, buses: ["B010"], add: -20 },
      { target: "demand" as const, zones: ["NG"], add: 300 },
    ];
    const out = placedPoints(changes, prepared([
      { target: "generation", matched: 30, elements: [] },
      { target: "demand", matched: 1, elements: [{ id: "B010", load_mw: [15, 0] }] },
      { target: "demand", matched: 6, elements: wide },
    ]), NETWORK);
    expect(out).toEqual([]);
    expect(placedPoints(changes, null, NETWORK)).toEqual([]);
  });
});
