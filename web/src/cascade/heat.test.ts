import { describe, expect, it } from "vitest";
import { heatLayers } from "./heat";
import type { DependencyNode, Network } from "./types";

const network: Network = {
  nodes: [
    { id: "B000", name: "S/E A", lon: -70, lat: -33, kv: 220, zone: "centro_sur", map_nodes: [] },
    { id: "B001", name: "S/E B", lon: -71, lat: -34, kv: 220, zone: "centro_sur", map_nodes: [] },
  ],
  lines: [],
};
const node = (over: Partial<DependencyNode>): DependencyNode => ({
  degree: 2, articulation: false, own_load_mw: 0, isolated_mw: 0, collateral_mw: 0, collateral_share: 0, collateral_people: 0,
  extra_loading: 0, lines_stressed: 0, criticality: 0, band: "ninguna", gen_mw: 0, people_fed: 0, share_of_people: 0, ...over,
});

describe("heat maps", () => {
  it("draws nothing when off or while its data is missing", () => {
    expect(heatLayers("none", { population: null, dependency: null, network })).toEqual([]);
    expect(heatLayers("population", { population: null, dependency: null, network })).toEqual([]);
    expect(heatLayers("dependency", { population: null, dependency: null, network })).toEqual([]);
  });

  it("builds one layer per kind once the data is there", () => {
    const dependency = { B000: node({ people_fed: 1000, criticality: 0.7 }), B001: node({}) };
    const d = { population: [[-70, -33, 5000]] as [number, number, number][], dependency, network };
    expect(heatLayers("population", d).map((l) => l.id)).toEqual(["heat-population"]);
    expect(heatLayers("dependency", d).map((l) => l.id)).toEqual(["heat-dependency"]);
    expect(heatLayers("criticality", d).map((l) => l.id)).toEqual(["heat-criticality"]);
  });
});
