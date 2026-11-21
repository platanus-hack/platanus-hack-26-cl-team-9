import linesUrl from "../../../data/processed/geo/lines.geojson?url";
import plantsUrl from "../../../data/processed/geo/plants.geojson?url";
import substationsUrl from "../../../data/processed/geo/substations.geojson?url";

/** Voltage groups of the Paper "Red" panel. `color` is the bar color in the design. */
export const VOLTAGE_BANDS: { label: string; minKv: number; color: string }[] = [
  { label: "500 kV", minKv: 500, color: "#f1f5f9" },
  { label: "154 a 345 kV", minKv: 154, color: "#f59e0b" },
  { label: "100 a 110 kV", minKv: 100, color: "#38bdf8" },
  { label: "44 a 69 kV", minKv: 44, color: "#7ba3c0" },
  { label: "Media tensión", minKv: 0, color: "#64748b" },
];

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
