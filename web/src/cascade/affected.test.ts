import { describe, expect, it } from "vitest";
import { affectedByComuna } from "./affected";
import type { BusState, ComunaPeople, Network } from "./types";

const net = {
  nodes: [
    { id: "B000", name: "S/E ALTO JAHUEL", lon: -70, lat: -33 },
    { id: "B001", name: "S/E CHARRUA", lon: -71, lat: -36 },
    { id: "B002", name: "S/E NUEVA", lon: -72, lat: -38 },
  ],
  lines: [],
} as unknown as Network;
const bus = (people: number): BusState => ({ gen_mw: 0, load_mw: 0, people });
const buses = { B000: bus(300), B001: bus(100), B002: bus(0) };
// comuna 1 is split over B000 (200) and B001 (100); comuna 2 is served by B000 alone.
const file: ComunaPeople = {
  source: "test", is_assumption: true,
  comunas: { "1": "Uno", "2": "Dos" },
  buses: { B000: [["1", 200], ["2", 100]], B001: [["1", 100]], B002: [] },
};

describe("affected population by comuna", () => {
  it("a comuna split over a dark and a lit bus is partial and estimated; a comuna with every bus dark is not", () => {
    const a = affectedByComuna(new Set(["B000"]), buses, net, file);
    expect(a.people).toBe(300);
    expect(a.rows).toEqual([
      { key: "1", name: "Uno", people: 200, total: 300, is_assumption: true },
      { key: "2", name: "Dos", people: 100, total: 100, is_assumption: false },
    ]);
  });

  it("all buses of a comuna dark: people equal the total", () => {
    const a = affectedByComuna(new Set(["B000", "B001"]), buses, net, file);
    expect(a.people).toBe(400);
    expect(a.rows[0]).toEqual({ key: "1", name: "Uno", people: 300, total: 300, is_assumption: false });
  });

  it("scales each bus's rows to its current people", () => {
    const a = affectedByComuna(new Set(["B000"]), { ...buses, B000: bus(600) }, net, file);
    expect(a.people).toBe(600);
    expect(a.rows.map((r) => [r.key, r.people])).toEqual([["1", 400], ["2", 200]]);
  });

  it("a dark bus without comuna rows becomes a row named after its substation, estimated", () => {
    const a = affectedByComuna(new Set(["B001"]), buses, net, null);
    expect(a).toEqual({ people: 100, rows: [{ key: "bus:B001", name: "Charrúa", people: 100, total: 100, is_assumption: true }] });
  });

  it("no dark buses: nobody affected", () => {
    expect(affectedByComuna(new Set(), buses, net, file)).toEqual({ people: 0, rows: [] });
  });
});
