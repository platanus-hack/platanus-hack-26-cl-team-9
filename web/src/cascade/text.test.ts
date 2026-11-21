import { describe, expect, it } from "vitest";
import { clock, conditionDate, conditionName } from "./text";

describe("operating condition labels", () => {
  it("takes the name from the label's parenthetical", () => {
    expect(conditionName("Noviembre 2026, 13:00 (mediodía solar)")).toBe("Mediodía solar");
    expect(conditionName("Noviembre 2026, 20:00 (punta nocturna)")).toBe("Punta nocturna");
    expect(conditionName("Febrero 2025, 03:00 (demanda mínima)")).toBe("Demanda mínima");
    expect(conditionName("Febrero 2025, 15:00 (referencia del 25F)")).toBe("Referencia 25F");
  });

  it("falls back to the whole label", () => {
    expect(conditionName("Marzo 2027, 10:00")).toBe("Marzo 2027, 10:00");
    expect(conditionName("Marzo 2027 ()")).toBe("Marzo 2027 ()");
  });

  it("writes the date line from the snapshot", () => {
    expect(conditionDate("2026-11-01 13:00")).toBe("1 nov 2026 · 13:00");
    expect(conditionDate("2025-02-01 03:00")).toBe("1 feb 2025 · 03:00");
    expect(conditionDate(undefined)).toBe("");
  });
});

describe("clock", () => {
  it("adds the simulated seconds to the snapshot time", () => {
    expect(clock("2025-02-01 15:00", 61.25)).toEqual({ hms: "15:01:01", tenths: "15:01:01,2" });
    expect(clock(undefined, 0).tenths).toBe("--:--:--,-");
  });
});
