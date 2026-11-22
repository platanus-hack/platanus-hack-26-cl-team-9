import { landOf, type Land } from "./regionLimit";

export type LonLat = [number, number];
/** [[west, south], [east, north]] in degrees, the shape Mapbox `fitBounds` and `maxBounds` take. */
export type Bounds = [LonLat, LonLat];

/** Where the camera goes for a network: the frame it fits, how far it may wander and the land its center must stay over. */
export interface CameraTarget {
  frame: Bounds;
  maxBounds: Bounds;
  /** null skips the over-land check (an uploaded network may be in a country without an outline). */
  land: Land | null;
}

// Margin around a frame, as a share of its larger side, so the tilted 3D view and a wide screen still fit inside maxBounds.
const FRAME_MARGIN = 0.04;
const MAX_MARGIN = 1;
const MIN_MAX_MARGIN_DEG = 8;
const MERCATOR_LAT = 85;

export function boundsOf(points: Iterable<LonLat>): Bounds | null {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  for (const [lon, lat] of points) {
    if (!Number.isFinite(lon) || !Number.isFinite(lat)) continue;
    w = Math.min(w, lon); e = Math.max(e, lon); s = Math.min(s, lat); n = Math.max(n, lat);
  }
  return w <= e ? [[w, s], [e, n]] : null;
}

export function union(a: Bounds, b: Bounds | null): Bounds {
  if (!b) return a;
  return [[Math.min(a[0][0], b[0][0]), Math.min(a[0][1], b[0][1])], [Math.max(a[1][0], b[1][0]), Math.max(a[1][1], b[1][1])]];
}

/** Grows a box by `share` of its larger side (at least `minDeg`) on every side, clamped to the Mercator world. */
export function pad(b: Bounds, share: number, minDeg = 0): Bounds {
  const d = Math.max(minDeg, share * Math.max(b[1][0] - b[0][0], b[1][1] - b[0][1]));
  return [[Math.max(-180, b[0][0] - d), Math.max(-MERCATOR_LAT, b[0][1] - d)], [Math.min(180, b[1][0] + d), Math.min(MERCATOR_LAT, b[1][1] + d)]];
}

export const contains = (b: Bounds, [lon, lat]: LonLat) => lon >= b[0][0] && lon <= b[1][0] && lat >= b[0][1] && lat <= b[1][1];

/** Every coordinate of a GeoJSON geometry, whatever its nesting. */
export function* coordinatesOf(coords: unknown): Generator<LonLat> {
  if (!Array.isArray(coords)) return;
  if (typeof coords[0] === "number") { yield [coords[0], coords[1] as number]; return; }
  for (const c of coords) yield* coordinatesOf(c);
}

interface OutlineFile { features: { properties?: Record<string, unknown> | null; geometry: { type: string; coordinates: unknown } }[] }

/** The features of one country: `shapeGroup` in latam/outlines.geojson (geoBoundaries); chile.geojson has no such field and is all Chile. */
export function outlineOf(file: OutlineFile, iso: string): OutlineFile {
  const tagged = file.features.some((f) => f.properties?.shapeGroup != null);
  return { features: tagged ? file.features.filter((f) => f.properties?.shapeGroup === iso) : file.features };
}

/**
 * Why: the frame comes from the network itself (its buses), not from a hand-written box, so it works for an uploaded
 * network too and stops where the grid stops (Chile's outline reaches Cape Horn, its grid ends near Chiloé). The outline,
 * when there is one, widens the area the camera may wander and gives the land it must stay over.
 */
export function cameraTarget(buses: Iterable<LonLat>, outline: OutlineFile | null): CameraTarget | null {
  const grid = boundsOf(buses);
  if (!grid) return null;
  const land = outline && outline.features.length ? landOf(outline as Parameters<typeof landOf>[0]) : null;
  const outlineBox = outline ? boundsOf(outline.features.flatMap((f) => [...coordinatesOf(f.geometry.coordinates)])) : null;
  return { frame: pad(grid, FRAME_MARGIN), maxBounds: pad(union(grid, outlineBox), MAX_MARGIN, MIN_MAX_MARGIN_DEG), land: land && land.length ? land : null };
}
