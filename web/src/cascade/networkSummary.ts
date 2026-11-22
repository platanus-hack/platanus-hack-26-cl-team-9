import { fetchJson } from "../lib/fetchJson";
import linesUrl from "../../../data/processed/geo/lines.geojson?url";
import plantsUrl from "../../../data/processed/geo/plants.geojson?url";
import substationsUrl from "../../../data/processed/geo/substations.geojson?url";
import type { RegionalCountry, RegionalGrid } from "../map/regional";
import { VOLTAGE_TIERS } from "./layers";

const SAMPLE_STROKES = [4, 3.5, 3, 2.5, 2];

/**
 * Voltage groups of the "Red" panel: the map's tiers (labels, kV limits and colors from `layers.ts`, so the panel cannot
 * drift from the map) with a thicker sample height in px (`stroke`), as in the design.
 */
export const VOLTAGE_BANDS: { label: string; minKv: number; color: string; stroke: number }[] = VOLTAGE_TIERS.map((t, i) => (
  { label: t.label, minKv: t.minKv, color: t.color, stroke: SAMPLE_STROKES[i] }
));

export interface NetworkSummary { km: number; substations: number; mw: number; kmByBand: number[] }
interface Collection<P> { features: { properties: P }[] }

/** Why: the "Red" panel states how big the whole grid is (all of the IDE Energía data, not only the 188-bus model). */
export async function loadNetworkSummary(): Promise<NetworkSummary> {
  const [lines, subs, plants] = await Promise.all([
    fetchJson<Collection<{ kv: number | null; length_km: number | null }>>(linesUrl),
    fetchJson<Collection<object>>(substationsUrl),
    fetchJson<Collection<{ mw: number | null }>>(plantsUrl),
  ]);
  return summarize(lines.features.map((f) => f.properties), subs.features.length, plants.features.map((f) => f.properties));
}

export function summarize(lines: { kv: number | null; length_km: number | null }[], substations: number, plants: { mw: number | null }[]): NetworkSummary {
  const kmByBand = VOLTAGE_BANDS.map(() => 0);
  for (const l of lines) {
    const band = VOLTAGE_BANDS.findIndex((b) => (l.kv ?? 0) >= b.minKv);
    if (l.kv != null && band >= 0) kmByBand[band] += l.length_km ?? 0;
  }
  const km = lines.reduce((sum, l) => sum + (l.length_km ?? 0), 0);
  return { km, substations, mw: plants.reduce((sum, p) => sum + (p.mw ?? 0), 0), kmByBand };
}

/** Another country's figures, from latam/manifest.json (the reduced layer `cascadasen-regional` wrote). */
export function summaryFromManifest(entry: RegionalCountry): NetworkSummary {
  const lines = Object.entries(entry.line_km_by_kv ?? {}).map(([kv, km]) => ({ kv: Number(kv), length_km: km }));
  return summarize(lines, entry.counts.substations, Object.values(entry.plant_mw_by_tech ?? {}).map((mw) => ({ mw })));
}

/** An uploaded network's figures, computed from the network itself; a line without length_km counts its drawn length. */
export function summaryFromGrid(grid: RegionalGrid): NetworkSummary {
  const lines = grid.lines.map((l) => ({ kv: l.kv, length_km: l.lengthKm ?? pathKm(l.path) }));
  return summarize(lines, grid.substations.length, grid.plants.map((p) => ({ mw: p.mw })));
}

const EARTH_KM = 6371.0088;
export function pathKm(path: [number, number][]): number {
  let km = 0;
  for (let i = 1; i < path.length; i++) {
    const [lon1, lat1] = path[i - 1].map((d) => (d * Math.PI) / 180), [lon2, lat2] = path[i].map((d) => (d * Math.PI) / 180);
    const h = Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2;
    km += 2 * EARTH_KM * Math.asin(Math.min(1, Math.sqrt(h)));
  }
  return km;
}
