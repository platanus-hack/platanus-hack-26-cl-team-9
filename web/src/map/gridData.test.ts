import { describe, expect, it } from "vitest";
import { aggregatePlantsByNode, type Substation } from "./gridData";
import { describeTopology, formatNumber } from "./nodeDetail";
import { formatPeople, narrate } from "../cascade/text";
import { LOADING_BANDS, loadingColor } from "../cascade/layers";
import type { Network } from "../cascade/types";

const SUBS: Substation[] = [
  { id: "A", name: "S/E A", kv: 220, position: [-70, -30] },
  { id: "B", name: "S/E B", kv: 110, position: [-71, -33] },
];

describe("aggregatePlantsByNode", () => {
  it("sums MW per node and keeps the technology with most MW", () => {
    const nodes = aggregatePlantsByNode(
      [
        { node: "A", tech: "solar", mw: 100 },
        { node: "A", tech: "termica", mw: 60 },
        { node: "A", tech: "termica", mw: 50 },
        { node: "B", tech: "hidro", mw: 20 },
      ],
      SUBS,
    );
    expect(nodes).toEqual([
      { id: "A", name: "S/E A", position: [-70, -30], tech: "termica", mw: 210 },
      { id: "B", name: "S/E B", position: [-71, -33], tech: "hidro", mw: 20 },
    ]);
  });

  it("skips plants without MW or with an unknown node", () => {
    const nodes = aggregatePlantsByNode(
      [
        { node: "A", tech: "solar", mw: null },
        { node: "Z", tech: "solar", mw: 10 },
      ],
      SUBS,
    );
    expect(nodes).toEqual([]);
  });
});

describe("node popup helpers", () => {
  it("labels where a line topology comes from", () => {
    expect(describeTopology("CEN Infotecnica (tramo oficial)", false)).toBe("oficial CEN");
    expect(describeTopology("inferida (geometría + nombre)", false)).toBe("inferida");
    expect(describeTopology("supuesto de acople", true)).toBe("supuesto de acople");
  });

  it("prints s/d for missing numbers", () => {
    expect(formatNumber(null)).toBe("s/d");
    expect(formatNumber(2800)).toBe("2.800");
  });
});

describe("cascade narration", () => {
  const network: Network = {
    nodes: [{ id: "B000", name: "S/E A", lon: 0, lat: 0, kv: 500, zone: "centro_sur", map_nodes: [] }, { id: "B001", name: "S/E B", lon: 0, lat: 0, kv: 500, zone: "centro_sur", map_nodes: [] }],
    lines: [{ id: "R000", a: "B000", b: "B001", kv: 500, capacity_mw: 100, x_pu: 0.01, map_edges: [], branches: [] }],
  };

  it("names the line in a cut and an overload", () => {
    const cut = { t: 0, type: "line_cut", ids: ["R000"], text_key: "line_cut", params: {} };
    expect(narrate(cut, network)).toBe("Se corta la línea A – B (500 kV).");
    expect(narrate({ ...cut, text_key: "line_overload_open" }, network)).toContain("supera el 120%");
  });

  it("explains why an island goes dark", () => {
    const e = { t: 1, type: "island_blackout", ids: [], text_key: "island_blackout", params: { buses: 3, load_mw: 58, reason: "no_inertia", min_hz: null } };
    expect(narrate(e, network)).toBe("Apagón en una isla de 3 barras (58 MW): no tiene inercia sincrónica.");
  });

  it("writes people in millions", () => {
    expect(formatPeople(15200000)).toContain("millones");
    expect(formatPeople(158000)).not.toContain("millones");
  });
});

describe("cascade colours", () => {
  it("colours a line by its loading, in the same bands the legend shows", () => {
    const edge = (loading: number) => ({ flow_mw: 100, status: "ok" as const, loading });
    expect(loadingColor(edge(0.5))).toEqual(LOADING_BANDS[0].color);
    expect(loadingColor(edge(0.6))).toEqual(LOADING_BANDS[0].color);
    expect(loadingColor(edge(0.75))).toEqual(LOADING_BANDS[1].color);
    expect(loadingColor(edge(0.95))).toEqual(LOADING_BANDS[2].color);
    expect(loadingColor(edge(1.3))).toEqual(LOADING_BANDS[3].color);
  });

  it("draws open lines and missing flows differently from loaded ones", () => {
    expect(loadingColor({ flow_mw: 0, status: "open", loading: 0 })).not.toEqual(LOADING_BANDS[0].color);
    expect(loadingColor(undefined)[3]).toBeLessThan(200);
  });
});
