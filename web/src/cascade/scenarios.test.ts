import { describe, expect, it } from "vitest";
import { activeDisaster, DISASTERS, keptNote } from "./Scenarios";

describe("Desastres", () => {
  it("has unique ids and every disaster changes something", () => {
    expect(new Set(DISASTERS.map((d) => d.id)).size).toBe(DISASTERS.length);
    expect(DISASTERS.every((d) => d.edits.lines.length + d.edits.buses.length > 0)).toBe(true);
  });

  it("shows the real date of the analogues, not the 2026 hour they run on", () => {
    expect(DISASTERS.find((d) => d.id === "2011")?.date).toBe("24 sep 2011 · 20:31");
    expect(DISASTERS.find((d) => d.id === "2010")?.date).toBe("14 mar 2010 · 20:43");
  });

  it("is active only at its hour and with exactly its changes, in any order", () => {
    expect(activeDisaster("nov2026-2000", { lines: [], buses: ["B043"] })?.id).toBe("2010");
    expect(activeDisaster("nov2026-2000", { lines: ["R006"], buses: [] })?.id).toBe("2011");
    expect(activeDisaster("feb2025-1500", { lines: ["R006"], buses: [] })).toBeNull();
    expect(activeDisaster("nov2026-2000", { lines: ["R006", "R001"], buses: [] })).toBeNull(); // one more cut: the user's own case
  });
});

describe("Desastres, real dates and figures", () => {
  it("dates the 25F at its real hour (D4)", () => {
    expect(DISASTERS[0].date).toBe("25 feb 2025 · 15:16");
  });
  it("carries the real event's figure with a source for each entry (F-06)", () => {
    expect(DISASTERS.map((d) => d.real?.text)).toEqual([
      "Evento real: unos 19 M de personas (98,5 %)",
      "Análogo en la red de 2026. Evento real: 9,8 M de personas",
      "Análogo en la red de 2026. Evento real: más de 13 M de personas",
    ]);
    expect(DISASTERS.every((d) => (d.real?.tip.length ?? 0) > 40)).toBe(true);
    expect(activeDisaster("feb2025-1500", { lines: ["R239"], buses: [] })?.real?.text).toContain("19 M");
  });
  it("says how many changes a condition keeps", () => {
    expect(keptNote(1)).toBe("Con 1 cambio tuyo");
    expect(keptNote(3)).toBe("Con 3 cambios tuyos");
  });
});
