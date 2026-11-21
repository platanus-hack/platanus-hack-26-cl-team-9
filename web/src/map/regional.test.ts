import { describe, expect, it } from "vitest";
import { buildRegionalLayers, regionalTooltip, type RegionalGrid } from "./regional";

const GRID: RegionalGrid = {
  countries: [],
  lines: [{ id: "BRA-L1", name: "LT A", kv: 500, lengthKm: 120.4, source: "EPE WebMap capa 23", path: [[-50, -10], [-51, -11]] }],
  substations: [{ id: "BRA-S1", name: "SE A", kv: 500, source: "EPE WebMap capa 22", position: [-50, -10] }],
  plants: [{ id: "BRA-P1", name: "UHE A", tech: "hidro", mw: 14000, source: "EPE WebMap capa 16", position: [-50, -10] }],
};

describe("regional layers", () => {
  it("draws lines, substations and plants under prefixed ids so they never trigger a cut", () => {
    const ids = buildRegionalLayers(GRID).map((l) => l.id);
    expect(ids).toEqual(["regional-lines", "regional-substations", "regional-plants"]);
    expect(ids.every((id) => id.startsWith("regional-"))).toBe(true);
  });

  it("tooltips carry the source and say the network is not simulated", () => {
    const line = regionalTooltip("regional-lines", GRID.lines[0])!;
    expect(line).toContain("500 kV");
    expect(line).toContain("120 km");
    expect(line).toContain("EPE WebMap capa 23");
    expect(line).toContain("no se simula");
    expect(regionalTooltip("regional-plants", GRID.plants[0])).toContain("14000 MW");
    expect(regionalTooltip("lines", GRID.lines[0])).toBeNull();
  });
});
