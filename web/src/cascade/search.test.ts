import { describe, expect, it } from "vitest";
import { findOption, searchOptions } from "./search";
import type { Network } from "./types";

describe("cold start search (D8)", () => {
  const network: Network = {
    nodes: [
      { id: "B1", name: "S/E CERRO NAVIA", lon: 0, lat: 0, kv: 220, zone: "CE", map_nodes: [] },
      { id: "B2", name: "S/E POLPAICO", lon: 0, lat: 0, kv: 500, zone: "CE", map_nodes: [] },
    ],
    lines: [
      { id: "R1", a: "B1", b: "B2", kv: 220, capacity_mw: 400, x_pu: 0.01, map_edges: [], branches: ["x"] },
      { id: "R2", a: "B1", b: "B2", kv: 220, capacity_mw: 300, x_pu: 0.01, map_edges: [], branches: ["y"] },
    ],
  };
  const options = searchOptions(network);
  it("lists every substation and line once, by name, with a number for repeated names", () => {
    expect(options.map((o) => o.value)).toEqual(["Cerro Navia", "Polpaico", "Cerro Navia – Polpaico (220 kV)", "Cerro Navia – Polpaico (220 kV) (2)"]);
    expect(options[0]).toMatchObject({ pick: { kind: "node", id: "B1" }, kind: "Subestación · 220 kV" });
  });
  it("finds the exact name first, then a unique partial match, ignoring accents and case", () => {
    expect(findOption(options, "polpaico")?.pick).toEqual({ kind: "node", id: "B2" });
    expect(findOption(options, "cerro navia – polpaico (220 kv) (2)")?.pick).toEqual({ kind: "line", id: "R2" });
    expect(findOption(options, "navia")).toBeNull(); // three matches: none chosen
    expect(findOption(options, "")).toBeNull();
  });
  it("finds a substation by its name without the owner tag", () => {
    const tagged = searchOptions({ ...network, nodes: network.nodes.map((n) => (n.id === "B2" ? { ...n, name: "S/E POLPAICO (TRANSELEC)" } : n)) });
    expect(findOption(tagged, "Polpaico")?.pick).toEqual({ kind: "node", id: "B2" });
  });
});
