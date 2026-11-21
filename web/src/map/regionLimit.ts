type Ring = number[][];
type Polygon = Ring[]; // first ring is the outline, the rest are holes
/** Land polygons of the countries the map may show. Why: a rectangle cannot follow Chile's coast, so the sea would stay reachable. */
export type Land = Polygon[];

const DIRECTIONS_DEG = [0, 45, 90, 135, 180, 225, 270, 315];

export function landOf(geojson: { features: { geometry: { type: string; coordinates: unknown } }[] }): Land {
  return geojson.features.flatMap(({ geometry }) =>
    geometry.type === "Polygon" ? [geometry.coordinates as Polygon] : geometry.type === "MultiPolygon" ? (geometry.coordinates as Polygon[]) : []);
}

function _inRing(ring: Ring, lng: number, lat: number): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if (yi > lat !== yj > lat && lng < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function onLand(land: Land, lng: number, lat: number): boolean {
  return land.some(([outline, ...holes]) => _inRing(outline, lng, lat) && !holes.some((hole) => _inRing(hole, lng, lat)));
}

/** True when land lies at most `radiusDeg` from the point (checked on 8 directions at two distances). */
export function nearLand(land: Land, lng: number, lat: number, radiusDeg: number): boolean {
  if (onLand(land, lng, lat)) return true;
  const squash = Math.cos((lat * Math.PI) / 180);
  return [0.5, 1].some((k) => DIRECTIONS_DEG.some((deg) => {
    const rad = (deg * Math.PI) / 180;
    return onLand(land, lng + (k * radiusDeg * Math.sin(rad)) / squash, lat + k * radiusDeg * Math.cos(rad));
  }));
}

/** Degrees covered by `fraction` of the shorter viewport side at a Mapbox zoom (512 px tiles). */
export function viewportRadiusDeg(zoom: number, widthPx: number, heightPx: number, fraction: number): number {
  return (Math.min(widthPx, heightPx) * fraction * 360) / (512 * 2 ** zoom);
}
