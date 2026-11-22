import type { BusState, ComunaPeople, HealthReport, Index, Network, Timeline } from "./types";

const cache = new Map<string, Promise<unknown>>();
export const MISSING = "Faltan datos de la simulación en esta versión de la app.";

function load<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    const request = fetch(`/cache/${path}`).then(async (r) => {
      // Some hosts answer a missing file with the SPA index.html and a 200. The file name goes to the console for whoever
      // runs the app (regenerate with `cascadasen-cache`); the screen says it in plain words (D11).
      if (!r.ok || !(r.headers.get("content-type") ?? "").includes("json")) {
        console.warn(`cache file missing: /cache/${path} (${r.status}); regenerate it with cascadasen-cache`);
        throw new Error(MISSING);
      }
      return r.json();
    });
    request.catch(() => cache.delete(path)); // a failed read is asked again on the next try
    cache.set(path, request);
  }
  return cache.get(path) as Promise<T>;
}

export const loadIndex = () => load<Index>("index.json");
export const loadNetwork = (year: number) => load<Network>(`network-${year}.json`);
export const loadBuses = (point: string) => load<Record<string, BusState>>(`${point}/buses.json`);
export const loadTimeline = (point: string, cut: string | "baseline") => load<Timeline>(`${point}/${cut}.json`);
/** Pre-fault health index and N-1 money at risk; null when the cache predates it (an old cache must not break the page). */
export const loadHealth = (point: string) => load<HealthReport>(`${point}/health.json`).catch(() => null);
export const loadComunas = (year: number) => load<ComunaPeople>(`comunas-${year}.json`).catch(() => null);
