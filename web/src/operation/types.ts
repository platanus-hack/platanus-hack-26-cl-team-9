// Strategic theatre on the mapa 3 network: contract in docs/mapa3.md section 10 and docs/stack.md 7.1.
import type { BusState, Frame, NetLine, NetNode, Network, Timeline } from "../cascade/types";

export interface TheaterArea { id: string; name: string; zone: string; lat: number; lon: number; population: number; buses: string[]; anchor_bus: string }
export interface TheaterNetwork extends Network {
  point: string; points: string[];
  nodes: (NetNode & { area: string })[];
  lines: (NetLine & { corridor: string | null })[];
  buses: Record<string, BusState>;
  areas: TheaterArea[];
  corridors: { id: string; a: string; b: string; lines: string[] }[];
  defenses: Record<string, string[]>;
  zones: string[];
}

export type Posture = "normal" | "manual" | "segmented";
export type Source = "scenario" | "user" | "adversary" | "external";
export interface Crew {
  id: string; base: string; position: string; bus: string; lon: number; lat: number;
  task: string | null; target: string | null; target_bus: string | null; arrival: number | null; status: "free" | "busy";
}
export interface CycleEvent { effect: string; type: string; target: string; area: string | null; source: Source; cause: string; status: string }
export interface Coa { action: string; target: string; proposer: string; rationale_key: string; params: Record<string, unknown> }
export interface Executed extends Coa { verdict: string; ok: boolean; crew?: string; arrival?: number }
export interface DecisionOut extends Coa { approved: boolean; reason: string; verdict: string }
export interface Metrics {
  cycle: number; demand_mw: number; served_mw: number; priority_demand_mw: number; priority_served_mw: number;
  observability: number; understood: boolean; resources_remaining: number; level: string; people_without_power: number;
}
export interface IsrPicture { p_intentional: number; leading_cause: string; confidence: number; affected: string[]; outages: string[]; rationale_key: string }

export interface TheaterSnapshot {
  cycle: number; t_min: number;
  events: CycleEvent[];
  grid: (Frame & { buses: Record<string, number> }) | null;
  transient: Timeline | null;
  areas: Record<string, { observability: number; posture: Posture; effects: { id: string; type: string; source: string }[] }>;
  crews: Crew[];
  estimated: { isr: IsrPicture };
  decisions: DecisionOut[];
  executed: Executed[];
  metrics: Metrics;
  real: { worst_level: string };
}

export interface AdversaryCfg { enabled: boolean; objective: string; adaptive: boolean; budget: number }
export interface RunSummary {
  run_id: string; status: "running" | "finished"; cycle: number; horizon: number; t_min: number;
  template: string; policy: string; seed: number; operating_point: string; adversary: AdversaryCfg; notice: string; replay_of?: string | null;
}
export interface Report {
  run: { policy: string; seed: number; finished: boolean };
  notice: string;
  indicators: { experimental: boolean; mission_continuity: number; priority_continuity: number; wrong_decisions: number; recoverability_cycles: number | null;
    situational_awareness: { time_to_understanding_cycles: number | null } };
  consequence: { worst_level: string; peak_people_without_power: number; unserved_energy_mwh: number; failure_cost_usd: number };
}
export interface AfterAction { question: string; notice: string; policy: string; summary: string[]; moments: string[]; adversary: string | null; narrative?: string; interpreter?: string }

export interface Catalog {
  templates: { id: string; label_key: string; operating_point: string; horizon: number; adversary: AdversaryCfg }[];
  policies: { id: string; label_key: string }[];
  objectives: string[];
  operating_points: string[];
}
export type Narrative = Record<string, Record<string, string> | string | number>;

export interface RunConfigIn { template: string; policy: string; point: string; adversary?: AdversaryCfg; seed?: number }
export interface CachedRun { run: RunSummary; snapshots: TheaterSnapshot[]; report: Report; after_action: AfterAction }
export interface CacheIndex { points: string[]; runs: { file: string; point: string; template: string; policy: string; seed: number }[]; notice: string }
