import type { BusState, HealthReport, Index, Network, Timeline } from "./types";

const cache = new Map<string, Promise<unknown>>();

function load<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(path, fetch(`/cache/${path}`).then(async (r) => {
      const missing = `Falta la caché (${path}). Genera el caché con cascadasen-cache.`;
      if (!r.ok) throw new Error(`${missing} Respuesta ${r.status}.`);
      // Some hosts answer a missing file with the SPA index.html and a 200
      if (!(r.headers.get("content-type") ?? "").includes("json")) throw new Error(missing);
      return r.json();
    }));
  }
  return cache.get(path) as Promise<T>;
}

export const loadIndex = () => load<Index>("index.json");
export const loadNetwork = (year: number) => load<Network>(`network-${year}.json`);
export const loadBuses = (point: string) => load<Record<string, BusState>>(`${point}/buses.json`);
export const loadTimeline = (point: string, cut: string | "baseline") => load<Timeline>(`${point}/${cut}.json`);
/** Pre-fault health index and N-1 money at risk; null when the cache predates it (an old cache must not break the page). */
export const loadHealth = (point: string) => load<HealthReport>(`${point}/health.json`).catch(() => null);
