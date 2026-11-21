import linesUrl from "../../../data/processed/geo/lines.geojson?url";
import plantsUrl from "../../../data/processed/geo/plants.geojson?url";
import substationsUrl from "../../../data/processed/geo/substations.geojson?url";
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
    _json<Collection<{ kv: number | null; length_km: number | null }>>(linesUrl),
    _json<Collection<object>>(substationsUrl),
    _json<Collection<{ mw: number | null }>>(plantsUrl),
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

async function _json<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`No se pudo cargar ${url}: ${r.status}`);
  return r.json();
}
