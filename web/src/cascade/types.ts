export interface PointInfo { id: string; label: string; year: number; snapshot: string }
export interface Index { points: PointInfo[]; assumptions: string[] }
export interface NetNode { id: string; name: string; lon: number; lat: number; kv: number; zone: string; map_nodes: string[] }
export interface NetLine { id: string; a: string; b: string; kv: number; capacity_mw: number; x_pu: number; map_edges: string[]; branches: string[] }
export interface Network { nodes: NetNode[]; lines: NetLine[] }
export interface BusState { gen_mw: number; load_mw: number; people: number }
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
