import { describe, expect, it } from "vitest";
import { NO_EDITS } from "../cascade/edits";
import type { Network, Timeline } from "../cascade/types";
import { cascadeEntries, diffEdits } from "./changelog";

const network: Network = {
  nodes: [{ id: "B1", name: "A", lon: 0, lat: 0, kv: 220, zone: "z", map_nodes: [] }],
  lines: [{ id: "R1", a: "B1", b: "B1", kv: 220, capacity_mw: 1, x_pu: 1, map_edges: [], branches: [] }],
};

describe("diffEdits", () => {
  it("logs a cut and a repair as adjustments", () => {
    const cut = diffEdits(NO_EDITS, { lines: ["R1"], buses: [] }, network);
    expect(cut).toHaveLength(1);
    expect(cut[0].kind).toBe("ajuste");
    expect(diffEdits({ lines: ["R1"], buses: [] }, NO_EDITS, network)[0].text).toContain("repuesta");
  });
  it("logs nothing when nothing changed", () => expect(diffEdits(NO_EDITS, NO_EDITS, network)).toEqual([]));
});

describe("cascadeEntries", () => {
  const tl = { events: [
    { t: 0, type: "line_cut", ids: ["R1"], text_key: "line_cut", params: {} },
    { t: 5, type: "line_overload_open", ids: ["R1"], text_key: "line_overload_open", params: {} },
    { t: 6, type: "island_stable", ids: [], text_key: "island_stable", params: {} },
  ] } as unknown as Timeline;
  it("keeps a disaster's first cut and every fall, drops stable notes", () => {
    expect(cascadeEntries(tl, network, new Set()).map((e) => e.when)).toEqual(["t+0 s", "t+5 s"]);
  });
  it("drops the cut the user made by hand", () => {
    expect(cascadeEntries(tl, network, new Set(["R1"])).map((e) => e.when)).toEqual(["t+5 s"]);
  });
});
