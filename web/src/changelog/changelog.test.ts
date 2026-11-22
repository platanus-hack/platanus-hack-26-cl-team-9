import { describe, expect, it } from "vitest";
import { NO_EDITS } from "../cascade/edits";
import type { Network, Timeline } from "../cascade/types";
import type { Prepared } from "../cascade/gridsApi";
import { cascadeEntries, diffEdits, withPrepared } from "./changelog";

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

describe("factor changes", () => {
  const off = { target: "generation" as const, tech: ["carbon"], factor: 0 };
  it("names the technology and the scope, and a new factor is one change", () => {
    const added = diffEdits(NO_EDITS, { lines: [], buses: [], changes: [off] }, network);
    expect(added.map((e) => e.text)).toEqual(["× 0 carbón en toda la red."]);
    const changed = diffEdits({ lines: [], buses: [], changes: [off] }, { lines: [], buses: [], changes: [{ ...off, factor: 0.5 }] }, network);
    expect(changed).toHaveLength(1);
    expect(changed[0].text).toContain("antes × 0");
  });
  it("attaches the substations the server resolved, by name when there is one", () => {
    const [entry] = diffEdits(NO_EDITS, { lines: [], buses: [], changes: [off] }, network);
    const prepared = { changes: [{ target: "generation", matched: 1, elements: [{ id: "B1" }] }] } as unknown as Prepared;
    const [out] = withPrepared([entry], [off], prepared, network);
    expect(out.ids).toEqual(["B1"]);
    expect(out.text).toContain("Subestación A");
  });
});
