import { describe, expect, it } from "vitest";
import { activeDisaster, DISASTERS } from "./Scenarios";

describe("Desastres", () => {
  it("has unique ids and every disaster changes something", () => {
    expect(new Set(DISASTERS.map((d) => d.id)).size).toBe(DISASTERS.length);
    expect(DISASTERS.every((d) => d.edits.lines.length + d.edits.buses.length > 0)).toBe(true);
  });

  it("is active only at its hour and with exactly its changes, in any order", () => {
    expect(activeDisaster("nov2026-2000", { lines: [], buses: ["B043"] })?.id).toBe("2010");
    expect(activeDisaster("nov2026-2000", { lines: ["R006"], buses: [] })?.id).toBe("2011");
    expect(activeDisaster("feb2025-1500", { lines: ["R006"], buses: [] })).toBeNull();
    expect(activeDisaster("nov2026-2000", { lines: ["R006", "R001"], buses: [] })).toBeNull(); // one more cut: the user's own case
  });
});
