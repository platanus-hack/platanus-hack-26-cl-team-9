import { describe, expect, it } from "vitest";
import { BUILT_IN, countryOf, DEFAULT_COUNTRY, networkFromParam } from "./country";

describe("country", () => {
  it("reads a missing field as Chile, so the cache published before the field still works", () => {
    expect(countryOf({})).toBe("CHL");
    expect(countryOf({ country: null })).toBe("CHL");
    expect(countryOf(undefined)).toBe("CHL");
    expect(countryOf({ country: "PER" })).toBe("PER");
  });
  it("only Chile's network can be simulated", () => {
    expect(BUILT_IN.filter((n) => n.simulable).map((n) => n.id)).toEqual([DEFAULT_COUNTRY]);
  });
  it("?pais= accepts an available ISO3 in any case and falls back to Chile", () => {
    const ids = BUILT_IN.map((n) => n.id);
    expect(networkFromParam("PER", ids)).toBe("PER");
    expect(networkFromParam("per", ids)).toBe("PER");
    expect(networkFromParam("XXX", ids)).toBe("CHL");
    expect(networkFromParam(null, ids)).toBe("CHL");
  });
});
