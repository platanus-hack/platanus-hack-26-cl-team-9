import { int, pct } from "../cascade/text";
import type { Timeline } from "../cascade/types";

/**
 * Ciberataque scenario in the web (docs/attack-sim.md section 3.2): types of `GET /sim/catalog` → `cyber_attack`, of the
 * `cyber` block of each run snapshot and of `report.cyber_attack`, and the pure helpers of the view. Everything is computed
 * by the backend; the web only builds the request from the catalog and shows the result. Area level only (docs/cyber.md 8).
 */
export type AreaState = "clean" | "compromised" | "struck" | "eradicated";
export type Outcome = "attack" | "defense" | "undecided";
export type Defense = "A" | "B" | "C" | "llm";
export interface CyberArea { id: string; name: string; zone: string }
export interface CyberCatalog {
  template: string; defaults: Record<string, number>; bounds: Record<string, [number, number]>; outcomes: Outcome[];
  crews_default: number; adjacency: Record<string, string[]>; areas: CyberArea[]; is_assumption: boolean;
}
export interface CyberEvent { cycle: number; kind: AreaState | "blocked" | "cleanup_failed"; area: string; from?: string }
export interface CyberFrame {
  cycle: number; t_min: number; areas: Record<string, AreaState>; counts: Record<AreaState, number>; outcome: Outcome | null;
  lost_share: number; people_without_power: number; crews_busy: number; events: CyberEvent[]; transient: Timeline | null;
}
export interface CyberReport {
  outcome: Outcome | null; start_area: string | null; params: Record<string, number>; peak_active_areas: number;
  ever_compromised: string[]; events: CyberEvent[]; is_assumption: boolean;
}

export const NOTICE = "Escenario hipotético: se modela el efecto, no el ataque.";
export const STATE_LABEL: Record<AreaState, string> = {
  clean: "sana", compromised: "comprometida", struck: "afectada", eradicated: "recuperada",
};
export const OUTCOME_LABEL: Record<Outcome, string> = {
  attack: "Gana el ataque: la red perdió el umbral de demanda",
  defense: "Gana la defensa: no queda intrusión y todo lo afectado se reparó",
  undecided: "Sin definir al terminar el horizonte",
};
export const DEFENSES: [Defense, string, string][] = [
  ["A", "A", "Reactiva"], ["B", "B", "Preventiva"], ["C", "C", "Adaptativa"], ["llm", "LLM", "Comandante LLM (elige entre acciones validadas)"],
];

/** The form fields, in this order, with their Spanish label and unit; values come from the catalog. */
export const FIELDS: { key: string; label: string; unit: "ciclos" | "prob" | "share" }[] = [
  { key: "strike_delay", label: "De comprometida a afectada", unit: "ciclos" },
  { key: "spread_cooldown", label: "Espera entre saltos", unit: "ciclos" },
  { key: "spread_p", label: "Probabilidad de salto a un vecino", unit: "prob" },
  { key: "isolation_p", label: "La segmentación frena el salto", unit: "prob" },
  { key: "eradicate_p", label: "La limpieza erradica la intrusión", unit: "prob" },
  { key: "clean_after_segmented", label: "Segmentación necesaria para limpiar", unit: "ciclos" },
  { key: "generation_share", label: "Generación que sale al afectar un área", unit: "share" },
  { key: "attack_win_lost_share", label: "Demanda perdida para que gane el ataque", unit: "share" },
];

/** The body of `POST /sessions/{sid}/runs`: only the parameters that differ from the catalog defaults are sent. */
export function runBody(cat: CyberCatalog, params: Record<string, number>, defense: Defense, crews: number, seed: number | null) {
  const changed = Object.fromEntries(Object.entries(params).filter(([k, v]) => cat.defaults[k] !== v));
  return {
    template: cat.template,
    policy: defense === "llm" ? "C" : defense,
    llm_commander: defense === "llm",
    capabilities: { field_crews: crews },
    adversary: { mode: "propagation", adaptive: false, budget: 0, objective: "complicate_recovery", ...(Object.keys(changed).length ? { propagation: changed } : {}) },
    ...(seed != null ? { seed } : {}),
  };
}

/** A parameter is valid when it is a number inside its catalog bounds. */
export function invalidFields(cat: CyberCatalog, params: Record<string, number>): string[] {
  return Object.entries(params).filter(([k, v]) => {
    const b = cat.bounds[k];
    return !b || !Number.isFinite(v) || v < b[0] || v > b[1];
  }).map(([k]) => k);
}

/** Frames from the step snapshots: only the ones with a `cyber` block. */
export function frames(snapshots: { cycle: number; t_min: number; cyber?: Omit<CyberFrame, "cycle" | "t_min" | "transient">; transient?: Timeline | null }[]): CyberFrame[] {
  return snapshots.filter((s) => s.cyber).map((s) => ({ ...s.cyber!, cycle: s.cycle, t_min: s.t_min, transient: s.transient ?? null }));
}

/** A cycle's events in Spanish, with area names. */
export function eventText(e: CyberEvent, name: (id: string) => string): string {
  const a = name(e.area);
  if (e.kind === "compromised") return e.from ? `La intrusión salta de ${name(e.from)} a ${a}.` : `La intrusión aparece en ${a}.`;
  if (e.kind === "struck") return `${a} pierde el despacho remoto y parte de su generación.`;
  if (e.kind === "eradicated") return `La defensa erradica la intrusión en ${a}.`;
  if (e.kind === "blocked") return `La segmentación frena el salto de ${e.from ? name(e.from) : "un área"} a ${a}.`;
  if (e.kind === "cleanup_failed") return `La limpieza de ${a} no erradicó la intrusión.`;
  return `${a}: ${e.kind}`;
}

export function frameFigures(f: CyberFrame) {
  const active = (f.counts.compromised ?? 0) + (f.counts.struck ?? 0);
  return [
    { label: "áreas con intrusión", value: int(active) },
    { label: "áreas recuperadas", value: int(f.counts.eradicated ?? 0) },
    { label: "demanda perdida", value: pct(f.lost_share) },
    { label: "personas sin luz", value: int(f.people_without_power) },
    { label: "cuadrillas ocupadas", value: int(f.crews_busy) },
  ];
}

/** Display value of a parameter (probabilities and shares as %, cycles as is) and the inverse. */
export const shown = (unit: string, v: number) => (unit === "ciclos" ? v : Math.round(v * 100));
export const stored = (unit: string, v: number) => (unit === "ciclos" ? Math.round(v) : v / 100);
