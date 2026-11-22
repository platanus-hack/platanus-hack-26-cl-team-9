import { describe, expect, it } from "vitest";
import { countryName, ISO3_CODES, isIso3 } from "./iso3";
describe("iso3", () => {
  it("recognises real alpha-3 codes only", () => {
    expect(isIso3("CHL")).toBe(true);
    expect(isIso3("chl")).toBe(false);
    expect(isIso3("XXX")).toBe(false);
    expect(isIso3(152)).toBe(false);
  });
  it("lists the codes sorted and without duplicates", () => {
    expect(ISO3_CODES).toContain("BRA");
    expect([...ISO3_CODES].sort()).toEqual(ISO3_CODES);
    expect(new Set(ISO3_CODES).size).toBe(ISO3_CODES.length);
  });
  it("gives the code back when it is unknown", () => {
    expect(countryName("XXX")).toBe("XXX");
  });
});
