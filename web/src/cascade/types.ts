export interface PointInfo { id: string; label: string; year: number; snapshot: string }
export interface Index { points: PointInfo[]; assumptions: string[] }
export type Origin = "base" | "session";
// origin, overridden, in_service and is_assumption only come from a session network (GET /api/v1/sessions/{sid}/network).
export interface NetNode { id: string; name: string; lon: number; lat: number; kv: number; zone: string; map_nodes: string[]; origin?: Origin; overridden?: boolean; in_service?: boolean; is_assumption?: boolean }
export interface NetLine { id: string; a: string; b: string; kv: number; capacity_mw: number; x_pu: number; map_edges: string[]; branches: string[]; origin?: Origin; overridden?: boolean; is_assumption?: boolean }
export interface Network { nodes: NetNode[]; lines: NetLine[] }
export interface BusState { gen_mw: number; load_mw: number; people: number; origin?: Origin; is_assumption?: boolean }
export interface EdgeState { flow_mw: number; status: "ok" | "overload" | "open"; loading: number }
export interface Frame { t: number; edges: Record<string, EdgeState>; dark: string[]; islands: { buses: number; gen_mw: number; load_mw: number }[] }
export interface Event { t: number; type: string; ids: string[]; text_key: string; params: Record<string, string | number | null> }
export interface Timeline {
  scenario: string; label: string; failed_elements: string[]; truncated: boolean; duration_s: number;
  events: Event[]; frames: Frame[]; frequency_hz: Record<string, [number, number][]>;
  summary: { people_without_power: number; load_shed_mw: number; load_total_mw: number; stages: number; lines_opened: string[]; dark_buses: number;
    islands: { result: string; min_hz: number | null; buses: number }[] };
  assumptions: string[];
}
/** A load or datacenter (D###) or a generator (G###) added by a session. Every value is an assumption. */
export interface SessionElement { id: string; bus: string; mw: number; name?: string; kind?: "datacenter" | "consumo"; tech?: string; synchronous?: boolean; inertia_h?: number; in_service?: boolean; origin: "session"; is_assumption: true }
export interface SessionWarning { code: string; ids: string[]; message: string }
export interface Balance { buses: Record<string, number>; redispatch_mw: number; is_assumption: true; rule: string }
/** GET /api/v1/sessions/{sid}/network: the mapa 3 network edited by the session overlay (docs/sessions-api.md section 10). */
export interface SessionNetwork extends Network {
  session_id: string; revision: number; dataset_revision: number; point: string; buses: Record<string, BusState>;
  loads: SessionElement[]; generators: SessionElement[]; out_of_service: { buses: string[]; lines: string[] };
  warnings: SessionWarning[]; balance: Balance[];
  baseline: { max_loading: number; overloaded: string[]; load_shed_mw: number; islands: Timeline["summary"]["islands"] };
}
