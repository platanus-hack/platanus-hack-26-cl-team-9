import type { NetNode } from "../cascade/types";

const R_KM = 6371;
const rad = (d: number) => (d * Math.PI) / 180;

export function haversineKm(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const a = Math.sin(rad(lat2 - lat1) / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(rad(lon2 - lon1) / 2) ** 2;
  return 2 * R_KM * Math.asin(Math.sqrt(a));
}

/** The in-service bus of at least minKv closest to a point (geometry only: the browser runs no physics). */
export function nearestBus(nodes: NetNode[], lon: number, lat: number, minKv = 220): { node: NetNode; km: number } | null {
  let best: { node: NetNode; km: number } | null = null;
  for (const node of nodes) {
    if (node.kv < minKv || node.in_service === false) continue;
    const km = haversineKm(lon, lat, node.lon, node.lat);
    if (!best || km < best.km) best = { node, km };
  }
  return best;
}
