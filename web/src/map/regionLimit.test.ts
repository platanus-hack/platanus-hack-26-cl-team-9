import { describe, expect, it } from "vitest";
import { landOf, nearLand, onLand, viewportRadiusDeg } from "./regionLimit";

const square = { features: [{ geometry: { type: "Polygon", coordinates: [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]] } }] };
const land = landOf(square);

describe("regionLimit", () => {
  it("tells land from sea", () => {
    expect(onLand(land, 1, 1)).toBe(true);
    expect(onLand(land, 5, 1)).toBe(false);
  });
  it("accepts a point near the coast and rejects open sea", () => {
    expect(nearLand(land, 2.4, 1, 0.5)).toBe(true);
    expect(nearLand(land, 5, 1, 0.5)).toBe(false);
  });
  it("shrinks the allowed margin as the zoom grows", () => {
    expect(viewportRadiusDeg(10, 1000, 800, 0.25)).toBeLessThan(viewportRadiusDeg(5, 1000, 800, 0.25));
  });
  it("loads the real Chile outline", async () => {
    const { readFileSync } = await import("node:fs");
    const chile = landOf(JSON.parse(readFileSync("../data/processed/chile.geojson", "utf8")));
    expect(onLand(chile, -70.65, -33.45)).toBe(true); // Santiago
    expect(onLand(chile, -78, -33.45)).toBe(false); // Pacific
    expect(onLand(chile, -64, -33.45)).toBe(false); // Argentina
  });
});
