import { describe, expect, it } from "vitest";
import { DEFAULT_SCENARIO, findScenario, SCENARIOS } from "./scenarios";

describe("scenarios", () => {
  it("finds the scenario for a point and cut, and null for a manual cut", () => {
    expect(findScenario("feb2025-1500", "R239")?.id).toBe("25f");
    expect(findScenario("feb2025-0300", null)?.id).toBe("noche-normal");
    expect(findScenario("feb2025-1500", "R001")).toBeNull();
  });

  it("has unique ids and a default that exists", () => {
    expect(new Set(SCENARIOS.map((s) => s.id)).size).toBe(SCENARIOS.length);
    expect(SCENARIOS).toContain(DEFAULT_SCENARIO);
  });
});
