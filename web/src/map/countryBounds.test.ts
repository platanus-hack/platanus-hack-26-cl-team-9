import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { boundsOf, cameraTarget, contains, outlineOf, pad, type LonLat } from "./countryBounds";
import { onLand } from "./regionLimit";

const json = (path: string) => JSON.parse(readFileSync(`../${path}`, "utf8"));
const outlines = json("data/processed/latam/outlines.geojson");
const chile = json("data/processed/chile.geojson");
/** Buses of each network as the app frames them: Chile's reduced network, the other countries' drawn substations. */
const BUSES: Record<string, LonLat[]> = {
  CHL: json("web/public/cache/network-2026.json").nodes.map((n: { lon: number; lat: number }) => [n.lon, n.lat]),
  ...Object.fromEntries(["ARG", "BOL", "BRA", "PER"].map((iso) => [iso, json(`data/processed/latam/${iso}/substations.geojson`).features.map((f: { geometry: { coordinates: LonLat } }) => f.geometry.coordinates)])),
};
const outline = (iso: string) => outlineOf(iso === "CHL" ? chile : outlines, iso);
const span = (b: [LonLat, LonLat]) => Math.max(b[1][0] - b[0][0], b[1][1] - b[0][1]);

describe("camera target per country (from the data, issue #49)", () => {
  for (const iso of Object.keys(BUSES)) {
    it(`${iso}: the frame holds every substation, maxBounds holds the frame, and the outline is the country's`, () => {
      const target = cameraTarget(BUSES[iso], outline(iso))!;
      expect(target).not.toBeNull();
      expect(BUSES[iso].length).toBeGreaterThan(10);
      expect(BUSES[iso].every((p) => contains(target.frame, p))).toBe(true);
      expect(contains(target.maxBounds, target.frame[0]) && contains(target.maxBounds, target.frame[1])).toBe(true);
      expect(target.land).not.toBeNull();
      // Most substations sit inside their own country's outline (the coast and borders are simplified).
      const inside = BUSES[iso].filter(([lon, lat]) => onLand(target.land!, lon, lat)).length;
      expect(inside / BUSES[iso].length).toBeGreaterThan(0.9);
    });
  }

  it("Chile's frame ends where its grid ends (near Chiloé), not at Cape Horn", () => {
    const frame = cameraTarget(BUSES.CHL, outline("CHL"))!.frame;
    expect(frame[0][1]).toBeGreaterThan(-46);
    expect(frame[1][1]).toBeLessThan(-16);
  });

  it("Brazil's frame and limits are far larger than Chile's, so they cannot share Chile's zoom limits", () => {
    const bra = cameraTarget(BUSES.BRA, outline("BRA"))!, chl = cameraTarget(BUSES.CHL, outline("CHL"))!;
    expect(bra.frame[1][0] - bra.frame[0][0]).toBeGreaterThan(3 * (chl.frame[1][0] - chl.frame[0][0]));
    expect(span(bra.maxBounds)).toBeGreaterThan(span(chl.maxBounds) * 0.9);
  });

  it("an uploaded network without an outline gets its frame from its own buses and no land check", () => {
    const target = cameraTarget([[10, 50], [12, 52]], null)!;
    expect(contains(target.frame, [10, 50]) && contains(target.frame, [12, 52])).toBe(true);
    expect(target.land).toBeNull();
    expect(cameraTarget([], null)).toBeNull();
  });

  it("boundsOf skips non-finite points and pad clamps to the Mercator world", () => {
    expect(boundsOf([[1, 2], [Number.NaN, 0], [3, -4]])).toEqual([[1, -4], [3, 2]]);
    expect(pad([[-179, -80], [179, 80]], 1)).toEqual([[-180, -85], [180, 85]]);
  });
});
