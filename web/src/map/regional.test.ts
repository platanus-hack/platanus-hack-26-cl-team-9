import { describe, expect, it } from "vitest";
import type { PathLayer } from "@deck.gl/layers";
import { hex, LOAD_BANDS, tierOf } from "../cascade/layers";
import { buildRegionalLayers, REGIONAL_NO_LOAD, regionalTooltip, type RegionalGrid } from "./regional";

const GRID: RegionalGrid = {
  countries: [],
  lines: [{ id: "BRA-R1", kv: 500, circuits: 2, lengthKm: 120.4, source: "EPE WebMap capa 23", path: [[-50, -10], [-51, -11]] }],
  substations: [{ id: "BRA-B1", name: "SE A", kv: 500, kind: "substation", source: "EPE WebMap capa 22", position: [-50, -10] }],
  plants: [{ id: "BRA-G1", name: "SE A", tech: "hidro", mw: 14000, count: 3, source: "EPE WebMap capa 16", position: [-50, -10] }],
};

describe("regional layers", () => {
  it("draws lines, substations and plants under prefixed ids so they never trigger a cut", () => {
    const ids = buildRegionalLayers(GRID).map((l) => l.id);
    expect(ids).toEqual(["regional-lines", "regional-substations", "regional-plants"]);
    expect(ids.every((id) => id.startsWith("regional-"))).toBe(true);
  });

  it("lines use Chile's voltage tiers, and a gray outside the load ramp in the load view", () => {
    const line = GRID.lines[0];
    const props = (mode: "voltage" | "load") => (buildRegionalLayers(GRID, mode)[0] as PathLayer<typeof line>).props;
    const color = (mode: "voltage" | "load") => (props(mode).getColor as (l: typeof line) => unknown)(line);
    expect(color("voltage")).toEqual(hex(tierOf(500).color));
    expect(color("load")).toEqual(hex(REGIONAL_NO_LOAD));
    expect(LOAD_BANDS.map((b) => b.color)).not.toContain(REGIONAL_NO_LOAD);
    expect((props("voltage").getWidth as (l: typeof line) => number)(line)).toBe(tierOf(500).width);
  });

  it("tooltips carry the source and say the network is not simulated", () => {
    const line = regionalTooltip("regional-lines", GRID.lines[0])!;
    expect(line).toContain("500 kV");
    expect(line).toContain("2 circuitos");
    expect(line).toContain("120 km");
    expect(line).toContain("EPE WebMap capa 23");
    expect(line).toContain("no se simula");
    expect(regionalTooltip("regional-plants", GRID.plants[0])).toContain("3 centrales");
    expect(regionalTooltip("regional-plants", GRID.plants[0])).toContain("14000 MW");
    expect(regionalTooltip("lines", GRID.lines[0])).toBeNull();
  });
});
