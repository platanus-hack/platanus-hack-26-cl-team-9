import { describe, expect, it } from "vitest";
import { heatPoints, needsDependency } from "./heat";
import type { DependencyNode, Network } from "./types";

const net = { nodes: [{ id: "B000", lon: -70, lat: -33 }, { id: "B001", lon: -71, lat: -34 }], lines: [] } as unknown as Network;
const buses = { B000: { gen_mw: 0, load_mw: 10, people: 500 }, B001: { gen_mw: 0, load_mw: 0, people: 0 } };
const dep = { B000: { people_fed: 0, criticality: 0 }, B001: { people_fed: 900, criticality: 0.5 } } as unknown as Record<string, DependencyNode>;

describe("heat maps", () => {
  it("population comes from the buses already loaded, without the server", () => {
    expect(needsDependency("population")).toBe(false);
    expect(heatPoints("population", net, buses, null)).toEqual([{ lon: -70, lat: -33, weight: 500 }]);
  });

  it("dependency and criticality wait for the server and drop substations with nothing to show", () => {
    expect(heatPoints("criticality", net, buses, null)).toEqual([]);
    expect(heatPoints("dependency", net, buses, dep)).toEqual([{ lon: -71, lat: -34, weight: 900 }]);
    expect(heatPoints("criticality", net, buses, dep)).toEqual([{ lon: -71, lat: -34, weight: 500000 }]);
  });
});
