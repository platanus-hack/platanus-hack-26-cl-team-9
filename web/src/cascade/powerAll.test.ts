import { describe, expect, it } from "vitest";
import { canPowerAll, powerAll, type PowerAllView } from "./powerAll";

describe("Prender todo: when it is enabled", () => {
  it("is disabled with no cuts and no edits", () => {
    expect(canPowerAll({ cuts: [], edited: false })).toBe(false);
  });

  it("is enabled with one cut", () => {
    expect(canPowerAll({ cuts: ["R239"], edited: false })).toBe(true);
  });

  it("is enabled with several cuts (a session's open lines)", () => {
    expect(canPowerAll({ cuts: ["R001", "R002", "sub-B010"], edited: false })).toBe(true);
  });

  it("is enabled with edits only", () => {
    expect(canPowerAll({ cuts: [], edited: true })).toBe(true);
  });
});

describe("Prender todo: what it resets", () => {
  it("keeps the point and clears the cut, the selection, the time and playback", () => {
    const view: PowerAllView = { pointId: "nov2026-1300", cut: "R001", selection: { kind: "node", id: "B010" }, t: 12.5, playing: true };
    expect(powerAll(view)).toEqual({ pointId: "nov2026-1300", cut: null, selection: null, t: 0, playing: false });
  });

  it("returns the 25F cut to the base case of the same hour", () => {
    const view: PowerAllView = { pointId: "feb2025-1500", cut: "R239", selection: { kind: "line", id: "R239" }, t: 20, playing: false };
    const next = powerAll(view);
    expect(next.pointId).toBe("feb2025-1500");
    expect(next.cut).toBeNull();
    expect(canPowerAll({ cuts: next.cut ? [next.cut] : [], edited: false })).toBe(false);
  });

  it("does not mutate its input", () => {
    const view: PowerAllView = { pointId: "feb2025-1500", cut: "R239", selection: null, t: 3, playing: true };
    powerAll(view);
    expect(view.cut).toBe("R239");
  });
});
