import { describe, expect, it } from "vitest";
import { scenarioOf } from "./useAssistant";

describe("scenarioOf", () => {
  it("reads the final grid of a prepare_scenario result", () => {
    const result = { scenario: { point: "feb2025-1500", changes: [{ target: "population", comunas: ["13201"], factor: 3 }, 5], open_lines: ["R239", 1], out_buses: [] } };
    expect(scenarioOf(result)).toEqual({ point: "feb2025-1500", changes: [{ target: "population", comunas: ["13201"], factor: 3 }], open_lines: ["R239"], out_buses: [] });
  });
  it("ignores anything else", () => {
    expect(scenarioOf(null)).toBeNull();
    expect(scenarioOf({ scenario: { changes: [] } })).toBeNull();
  });
});
