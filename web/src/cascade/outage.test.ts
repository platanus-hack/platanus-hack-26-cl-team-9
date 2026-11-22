import { describe, expect, it } from "vitest";
import { batches, isSwitchedOff } from "./outage";
import type { NetLine, Network } from "./types";

const line = (id: string, a: string, b: string): NetLine => ({ id, a, b, kv: 220, capacity_mw: 100, x_pu: 0.1, map_edges: [], branches: [id] });
const NET: Network = {
  nodes: [],
  lines: [line("R1", "B1", "B2"), line("R2", "B2", "B3"), line("R3", "B3", "B1"), line("R4", "B3", "B4")],
};
const L = (id: string) => ({ kind: "line" as const, id });
const N = (id: string) => ({ kind: "node" as const, id });
const open = (...lines: string[]) => ({ lines, buses: [] });

describe("switched off, in a session (open lines)", () => {
  it("a substation is off only when all its lines are open", () => {
    expect(isSwitchedOff(N("B1"), NET, open("R1", "R3"), true)).toBe(true);
    expect(isSwitchedOff(N("B1"), NET, open("R1"), true)).toBe(false);
    expect(isSwitchedOff(N("B9"), NET, open(), true)).toBe(false);
  });

  it("a line is off when it is open", () => {
    expect(isSwitchedOff(L("R2"), NET, open("R2"), true)).toBe(true);
    expect(isSwitchedOff(L("R2"), NET, open(), true)).toBe(false);
  });
});

describe("switched off, without a session (local changes)", () => {
  it("a line is off when it is among the cut lines", () => {
    expect(isSwitchedOff(L("R2"), NET, { lines: ["R2"], buses: [] }, false)).toBe(true);
    expect(isSwitchedOff(L("R1"), NET, { lines: ["R2"], buses: [] }, false)).toBe(false);
  });

  it("a substation is off when it is among the buses out of service, not because its lines are cut", () => {
    expect(isSwitchedOff(N("B3"), NET, { lines: [], buses: ["B3"] }, false)).toBe(true);
    expect(isSwitchedOff(N("B1"), NET, { lines: ["R1", "R3"], buses: [] }, false)).toBe(false);
  });

  it("the lines of a substation out of service are not off by themselves", () => {
    expect(isSwitchedOff(L("R4"), NET, { lines: [], buses: ["B3"] }, false)).toBe(false);
  });
});

describe("cut batches", () => {
  it("splits ids into batches of three for the cut route", () => {
    expect(batches(["a", "b", "c", "d", "e", "f", "g"])).toEqual([["a", "b", "c"], ["d", "e", "f"], ["g"]]);
    expect(batches([])).toEqual([]);
  });
});
