import type { RegionalCountry, RegionalLine, RegionalPlant, RegionalSubstation } from "../map/regional";
import type { BusState, DependencyNode, Network, Timeline } from "./types";

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

/** What the outages themselves take away, before any cascade. */
export interface DirectLoss { load_mw: number; gen_mw: number; people: number }
export interface SimulationResult {
  point: string; open_lines: string[]; out_buses: string[]; dropped_lines: string[]; direct: DirectLoss;
  warnings: { code: string; message: string }[]; timeline: Timeline;
}
/** The cascade with several changes applied together (`POST /grids/simulate`): the cache only has single cuts. */
export const simulateGrid = (body: { point: string; open_lines: string[]; out_buses: string[] }) =>
  request<SimulationResult>("simulate", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

/** Cost of the outage (`POST /grids/cost`, issue #82). Every value comes from the backend with its source or assumption. */
export interface OutageCost {
  energy_not_served_mwh: number; cost_usd: number;
  outage_hours: { value: number; is_assumption?: boolean; note?: string };
  unserved_cost_usd_per_mwh: { value: number; source?: string; is_assumption?: boolean };
  assumptions: string[];
}
/** null while the backend has no cost endpoint (404): the panel says it is pending instead of estimating it. */
export async function loadOutageCost(body: { point: string; open_lines: string[]; out_buses: string[] }): Promise<OutageCost | null> {
  const r = await fetch("/api/v1/grids/cost", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  if (r.status === 404 || r.status === 405) return null;
  if (!r.ok) throw new Error(`No se pudo calcular el costo (${r.status}).`);
  return r.json();
}

/** Heat-map data of the grid as it stands after the changes (`POST /grids/dependency`): about 2 s per new set of changes. */
export const loadDependency = (body: { point: string; open_lines: string[]; out_buses: string[] }) =>
  request<{ point: string; open_lines: string[]; nodes: Record<string, DependencyNode> }>("dependency", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
