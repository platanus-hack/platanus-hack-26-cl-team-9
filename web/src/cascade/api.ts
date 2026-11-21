import type { BusState, Index, Network, Timeline } from "./types";

const cache = new Map<string, Promise<unknown>>();

function load<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(path, fetch(`/cache/${path}`).then((r) => {
      if (!r.ok) throw new Error(`No se pudo cargar ${path}: ${r.status}. Genera el caché con cascadasen-cache.`);
      return r.json();
    }));
  }
  return cache.get(path) as Promise<T>;
}

export const loadIndex = () => load<Index>("index.json");
export const loadNetwork = (year: number) => load<Network>(`network-${year}.json`);
export const loadBuses = (point: string) => load<Record<string, BusState>>(`${point}/buses.json`);
export const loadTimeline = (point: string, cut: string | "baseline") => load<Timeline>(`${point}/${cut}.json`);
