import { describe, expect, it } from "vitest";
import { aggregatePlantsByNode, type Substation } from "./gridData";
import { describeTopology, formatNumber } from "./nodeDetail";

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
