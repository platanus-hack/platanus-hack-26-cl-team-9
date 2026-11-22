import { describe, expect, it } from "vitest";
import { RECTANGLE_BASE, SQUARE_BASE } from "./shapes";
describe("shapes", () => {
  it("centres both base shapes on the origin", () => {
    for (const shape of [SQUARE_BASE, RECTANGLE_BASE]) {
      expect(shape).toHaveLength(4);
      expect(shape.reduce((s, p) => s + p[0], 0)).toBeCloseTo(0);
      expect(shape.reduce((s, p) => s + p[1], 0)).toBeCloseTo(0);
    }
  });
  it("keeps the rectangle wider than tall and the square even", () => {
    expect(RECTANGLE_BASE[1][0] - RECTANGLE_BASE[0][0]).toBeGreaterThan(RECTANGLE_BASE[2][1] - RECTANGLE_BASE[1][1]);
    expect(SQUARE_BASE[1][0] - SQUARE_BASE[0][0]).toBeCloseTo(SQUARE_BASE[2][1] - SQUARE_BASE[1][1]);
  });
});
