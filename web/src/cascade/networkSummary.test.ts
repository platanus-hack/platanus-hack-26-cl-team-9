import { describe, expect, it } from "vitest";
import { summarize } from "./networkSummary";

describe("network summary", () => {
  it("groups km by voltage band and sums installed MW", () => {
    const lines = [{ kv: 500, length_km: 100 }, { kv: 220, length_km: 50 }, { kv: 154, length_km: 10 }, { kv: 110, length_km: 20 }, { kv: 66, length_km: 5 }, { kv: 23, length_km: 2 }, { kv: null, length_km: 7 }];
    const s = summarize(lines, 3, [{ mw: 10.5 }, { mw: null }, { mw: 4 }]);
    expect(s.kmByBand).toEqual([100, 60, 20, 5, 2]);
    expect(s.km).toBe(194);
    expect(s).toMatchObject({ substations: 3, mw: 14.5 });
  });
});
