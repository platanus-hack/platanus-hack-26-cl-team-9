import type { RegionalCountry, RegionalLine, RegionalPlant, RegionalSubstation } from "../map/regional";
import type { BusState, Network } from "./types";

/** Grid documents served by the backend from S3 (docs/grids.md): catalogue, compose and the context documents. */
export interface CatalogPoint { key: string; point: string; label: string; year: number; snapshot: string }
export interface CatalogScenario { id: string; name: string; point: string; open_lines: string[]; edits: boolean }
export interface CatalogContext { key: string; country: string; name: string; bytes: number; lines: number; substations: number; plants: number }
export interface CatalogDocument { key: string; country: string; role: string; bytes: number }
export interface CatalogGrid { country: string; name: string; status: "Complete" | "Partial"; key: string | null }
export interface Catalog { built_at: string; documents: CatalogDocument[]; grids: CatalogGrid[]; points: CatalogPoint[]; scenarios: CatalogScenario[]; context: CatalogContext[] }
export interface ComposeRequest { point?: string; scenario?: string; context: string[] }
export interface ComposedGrid {
  point: string; label: string; year: number; scenario: string | null; built_at: string; open_lines: string[];
  network: Network; operating: Record<string, BusState>; context: string[]; sources: { key: string; sha256: string }[];
}
export interface ContextDocument { country: string; meta: RegionalCountry; lines: RegionalLine[]; substations: RegionalSubstation[]; plants: RegionalPlant[] }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`/api/v1/grids/${path}`, init);
  if (!r.ok) {
    const detail = await r.json().then((b) => b.detail).catch(() => null);
    throw new Error(typeof detail === "string" ? detail : `No se pudo leer las fuentes (${r.status}).`);
  }
  return r.json();
}

export const loadCatalog = () => request<Catalog>("sources");
export const composeGrid = (body: ComposeRequest) =>
  request<ComposedGrid>("compose", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
export const loadContextDocument = (key: string) => request<ContextDocument>(`documents/${key}`);
