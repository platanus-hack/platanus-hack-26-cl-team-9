import type { RegionalCountry, RegionalLine, RegionalPlant, RegionalSubstation } from "../map/regional";
import type { StressChange } from "./edits";
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
/** People a generating substation should feed before the failure against the people it still feeds after it. */
export interface SupplyRow { id: string; name: string; zone: string; gen_mw: [number, number]; should_feed: number; feeds: number; pct_fed: number }
export interface ZoneSupply { should_feed: number; feeds: number; pct_fed: number }
export interface Supply { sources: SupplyRow[]; by_zone: Record<string, ZoneSupply> }
export interface SimulationResult {
  point: string; open_lines: string[]; out_buses: string[]; dropped_lines: string[]; direct: DirectLoss;
  warnings: { code: string; message: string }[]; timeline: Timeline; supply?: Supply;
}
/** Failures plus the prepared scenario, the body of simulate, dependency and cost. */
export interface GridChanges { point: string; open_lines: string[]; out_buses: string[]; changes?: StressChange[] }
/** The cascade with several changes applied together (`POST /grids/simulate`): the cache only has single cuts. */
export const simulateGrid = (body: GridChanges) =>
  request<SimulationResult>("simulate", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

/** Cost of the outage (`POST /grids/cost`, docs/engine.md "Cost"). Every value comes from the backend with its source or assumption. */
export interface OutageCost {
  energy_not_served_mwh: number; cost_usd: number; cost_per_hour_usd: number;
  breakdown: { dark_mw: number; shed_mw: number; dark_share: number; total_blackout_factor: number };
  outage_hours: { value: number; is_assumption?: boolean; note?: string };
  unserved_cost_usd_per_mwh: { value: number; source?: string; is_assumption?: boolean };
  assumptions: string[];
}
/** null while the backend has no cost endpoint (404): the panel says it is pending instead of estimating it. */
export async function loadOutageCost(body: GridChanges): Promise<OutageCost | null> {
  const r = await fetch("/api/v1/grids/cost", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  if (r.status === 404 || r.status === 405) return null;
  if (!r.ok) throw new Error(`No se pudo calcular el costo (${r.status}).`);
  return r.json();
}

/** Heat-map data of the grid as it stands after the changes (`POST /grids/dependency`). With `criticality: false` only
 *  who feeds whom comes back, in milliseconds; criticality runs one cascade per substation and takes seconds. */
export const loadDependency = (body: GridChanges & { criticality: boolean }) =>
  request<{ point: string; open_lines: string[]; nodes: Record<string, DependencyNode> }>("dependency", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });

/** One element a change touched, before and after (`[before, after]`). */
export interface PreparedElement { id: string; name?: string; load_mw?: [number, number]; gen_mw?: [number, number]; people?: number; capacity_mw?: [number, number] }
/** Where a place of a change went: the one substation it resolved to, and how (Spanish, shown as is). */
export interface PreparedPlace { place: string; bus: string; bus_name: string; how: string }
export interface PreparedChange {
  target: string; matched: number; people_delta?: number; load_delta_mw?: number; gen_delta_mw?: number; elements?: PreparedElement[];
  places?: PreparedPlace[]; tech?: string[]; new_plant?: boolean;
}
/** The grid of a prepared scenario with no failure (`POST /grids/prepare`, docs/stress.md). */
export interface Prepared {
  point: string; changes: PreparedChange[]; per_capita_w: number;
  totals: { people_total: number; load_total_mw: number; gen_total_mw: number };
  overloaded_lines: { id: string; kv: number; loading_pct: number }[];
  should_feed: Supply;
  assumptions: { id: string; text: string; source?: string; is_assumption: boolean }[];
}
export const prepareScenario = (body: { point: string; changes: StressChange[] }) =>
  request<Prepared>("prepare", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
