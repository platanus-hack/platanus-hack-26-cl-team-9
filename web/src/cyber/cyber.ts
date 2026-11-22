import { int, pct } from "../cascade/text";
import type { Frame, Timeline } from "../cascade/types";

/**
 * Ciberataque monitor (docs/attack-sim.md section 3.2): types of `GET /sim/catalog` → `cyber_attack`, of the `cyber` block
 * of each run snapshot and of `report.cyber_attack`, and the pure helpers of the view. Every value comes from the backend;
 * the web only builds requests from the catalog and lays out the result. Operating-area level only (docs/cyber.md 8).
 */
export type AreaState = "clean" | "compromised" | "struck" | "eradicated";
export type Outcome = "attack" | "defense" | "undecided";
/** Who defends: a rules policy, the server's LLM commander, or the user by hand (turn by turn). */
export type Defense = "A" | "B" | "C" | "llm" | "user";
export interface CyberArea { id: string; name: string; zone: string; population: number; lon: number | null; lat: number | null }
export interface DefenseActionSpec { action: string; label: string; role: string }
export interface Preset { id: string; label: string; params: Record<string, number>; measured?: string }
export interface CyberCatalog {
  template: string; defaults: Record<string, number>; presets?: Preset[]; bounds: Record<string, [number, number]>; outcomes: Outcome[];
  crews_default: number; adjacency: Record<string, string[]>; areas: CyberArea[]; defense_actions?: DefenseActionSpec[]; is_assumption: boolean;
}
export interface CyberEvent { cycle: number; kind: AreaState | "blocked" | "cleanup_failed"; area: string; from?: string }
export interface DefenseAction { action: string; target: string; ok: boolean; verdict?: string; proposer?: string }
export interface CyberFrame {
  cycle: number; t_min: number; areas: Record<string, AreaState>; counts: Record<AreaState, number>; outcome: Outcome | null;
  lost_share: number; people_without_power: number; crews_busy: number; events: CyberEvent[]; transient: Timeline | null;
  people_out?: Record<string, number>; segmented?: string[]; dark?: string[]; defense_actions?: DefenseAction[];
  /** The grid at the end of the cycle (snapshot `grid`, the map's Frame format): what the map draws for this cycle. */
  grid: Frame | null;
}
export interface CyberReport {
  outcome: Outcome | null; start_area: string | null; params: Record<string, number>; peak_active_areas: number;
  ever_compromised: string[]; events: CyberEvent[]; is_assumption: boolean;
}

export const NOTICE = "Escenario hipotético: se modela el efecto, no el ataque.";
export const OUTCOME_LABEL: Record<Outcome, string> = {
  attack: "Gana el ataque: la red perdió el umbral de demanda",
  defense: "Gana la defensa: no queda intrusión y todo lo afectado se reparó",
  undecided: "Sin definir al terminar el horizonte",
};
export const DEFENSES: [Defense, string, string][] = [
  ["A", "A", "Algoritmo reactivo"], ["B", "B", "Algoritmo preventivo"], ["C", "C", "Algoritmo adaptativo"],
  ["llm", "LLM", "Comandante LLM: elige entre acciones ya validadas"], ["user", "Usuario", "Tú defiendes, turno a turno"],
];
export const DEFENSE_NAME: Record<Defense, string> = { A: "algoritmo A", B: "algoritmo B", C: "algoritmo C", llm: "comandante LLM", user: "usuario" };

/** What the monitor shows for an area: the attack's side (red), the defence's side (blue) or untouched (grey). */
export type Status = "dark" | "struck" | "compromised" | "shielded" | "recovered" | "clean";
export const STATUS_LABEL: Record<Status, string> = {
  dark: "Sin luz", struck: "Afectada", compromised: "En disputa", shielded: "Blindada", recovered: "Recuperada", clean: "Con luz",
};
export const SIDE: Record<Status, "attack" | "defense" | "none"> = {
  dark: "attack", struck: "attack", compromised: "attack", shielded: "defense", recovered: "defense", clean: "none",
};

/**
 * The state shown for an area. A hit area the defence has segmented is "En disputa": both sides are on it. `hideLatent`
 * (the user defends and the run is on) shows a latent intrusion as "Con luz", since the defence cannot see it either.
 */
export function statusOf(f: CyberFrame, id: string, hideLatent = false): Status {
  if (f.dark?.includes(id)) return "dark";
  const st = f.areas[id] ?? "clean";
  const segmented = !!f.segmented?.includes(id);
  if (st === "struck") return segmented ? "compromised" : "struck";
  if (st === "compromised" && !hideLatent) return "compromised";
  if (segmented) return "shielded";
  return st === "eradicated" ? "recovered" : "clean";
}

/** The two counters: areas the attack holds and people without power; areas the defence holds and the people in them. */
export function scoreboard(f: CyberFrame, areas: CyberArea[], hideLatent = false) {
  const st = areas.map((a) => ({ a, s: statusOf(f, a.id, hideLatent) }));
  const attack = st.filter((x) => x.s === "dark" || x.s === "struck");
  const defense = st.filter((x) => SIDE[x.s] === "defense");
  return {
    attackAreas: attack.length,
    disputed: st.filter((x) => x.s === "compromised").length,
    peopleOut: f.people_without_power,
    defenseAreas: defense.length,
    protectedPeople: defense.reduce((n, x) => n + x.a.population, 0),
  };
}

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
    policy: defense === "llm" || defense === "user" ? "C" : defense,
    llm_commander: defense === "llm",
    manual_defense: defense === "user",
    capabilities: { field_crews: crews },
    adversary: { mode: "propagation", adaptive: false, budget: 0, objective: "complicate_recovery", ...(Object.keys(changed).length ? { propagation: changed } : {}) },
    ...(seed != null ? { seed } : {}),
  };
}

/** The preset whose values the form holds now, if any (the user may edit a value and leave every preset). */
export function activePreset(cat: CyberCatalog, params: Record<string, number>): Preset | null {
  return cat.presets?.find((p) => Object.entries(p.params).every(([k, v]) => params[k] === v)) ?? null;
}

/** A parameter is valid when it is a number inside its catalog bounds. */
export function invalidFields(cat: CyberCatalog, params: Record<string, number>): string[] {
  return Object.entries(params).filter(([k, v]) => {
    const b = cat.bounds[k];
    return !b || !Number.isFinite(v) || v < b[0] || v > b[1];
  }).map(([k]) => k);
}

type Snap = { cycle: number; t_min: number; cyber?: Omit<CyberFrame, "cycle" | "t_min" | "transient" | "grid">; transient?: Timeline | null; grid?: Omit<Frame, "t"> | null };
/** Frames from the step snapshots: only the ones with a `cyber` block. */
export function frames(snapshots: Snap[]): CyberFrame[] {
  return snapshots.filter((s) => s.cyber).map((s) => ({
    ...s.cyber!, cycle: s.cycle, t_min: s.t_min, transient: s.transient ?? null, grid: s.grid ? { t: 0, ...s.grid } : null,
  }));
}

/** A cycle's attack events in Spanish, with area names. */
export function eventText(e: CyberEvent, name: (id: string) => string): string {
  const a = name(e.area);
  if (e.kind === "compromised") return e.from ? `La intrusión salta de ${name(e.from)} a ${a}.` : `La intrusión aparece en ${a}.`;
  if (e.kind === "struck") return `${a} pierde el despacho remoto y parte de su generación.`;
  if (e.kind === "eradicated") return `La defensa erradica la intrusión en ${a}.`;
  if (e.kind === "blocked") return `La segmentación frena el salto de ${e.from ? name(e.from) : "un área"} a ${a}.`;
  if (e.kind === "cleanup_failed") return `La limpieza de ${a} no erradicó la intrusión.`;
  return `${a}: ${e.kind}`;
}

const ACTION_VERB: Record<string, string> = {
  digital_segmentation: "segmenta", restore_element: "envía una cuadrilla a reparar", manual_operation: "toma operación local en",
  backup_comms: "activa comunicaciones de respaldo en", field_verification: "verifica en terreno", fast_reserve: "usa reserva rápida en",
  battery_support: "usa baterías en", preventive_load_reduction: "reduce carga en", rearm_defense: "rearma", request_external_support: "pide apoyo para",
};
/** A defence action in Spanish: "La defensa segmenta Copiapó" or why it could not. */
export function actionText(d: DefenseAction, name: (id: string) => string): string {
  const what = `${ACTION_VERB[d.action] ?? d.action} ${name(d.target)}`;
  return d.ok ? `La defensa ${what}.` : `La defensa no pudo: ${what} (${verdictText(d.verdict)}).`;
}
const VERDICTS: Record<string, string> = {
  insufficient_resources: "sin recursos libres", no_crew_in_range: "ninguna cuadrilla llega a tiempo", failed: "falló al primer intento",
  remote_command_not_acknowledged: "sin control remoto: primero operación local", attention_saturated: "sin atención del operador",
};
const verdictText = (v?: string) => (v ? VERDICTS[v] ?? v.replace(/_/g, " ") : "rechazada");

export const millions = (n: number) => `${(n / 1e6).toLocaleString("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} M`;
export const figures = (f: CyberFrame) => [
  { label: "demanda perdida", value: pct(f.lost_share) },
  { label: "cuadrillas ocupadas", value: int(f.crews_busy) },
];

/** Display value of a parameter (probabilities and shares as %, cycles as is) and the inverse. */
export const shown = (unit: string, v: number) => (unit === "ciclos" ? v : Math.round(v * 100));
export const stored = (unit: string, v: number) => (unit === "ciclos" ? Math.round(v) : v / 100);

/**
 * Lays out the map labels of the monitor after the overlay loop placed each area dot (`data-px`, `data-py`): labels
 * stack in a column at `columnX` in north-to-south order, at least `gap` px apart, and a leader line joins each one to
 * its dot. Pure DOM work on the elements the overlay renders; no data is computed here.
 */
export function layoutTags(root: HTMLElement, columnX: number, gap = 30): void {
  const els = [...root.querySelectorAll<HTMLElement>(".cy-tag-anchor")];
  const placed = els.map((el) => ({ el, x: Number(el.dataset.px), y: Number(el.dataset.py) })).filter((p) => Number.isFinite(p.x));
  placed.sort((a, b) => a.y - b.y);
  let prev = -Infinity;
  for (const p of placed) {
    const y = Math.max(p.y, prev + gap);
    prev = y;
    const dx = columnX - p.x, dy = y - p.y;
    const tag = p.el.querySelector<HTMLElement>(".cy-tag");
    const line = p.el.querySelector<SVGLineElement>("line");
    if (tag) tag.style.transform = `translate(${dx.toFixed(1)}px, ${(dy - 12).toFixed(1)}px)`;
    if (line) { line.setAttribute("x2", (dx - 2).toFixed(1)); line.setAttribute("y2", dy.toFixed(1)); }
  }
}
