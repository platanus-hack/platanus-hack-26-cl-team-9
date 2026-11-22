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
/** Outcome titles (decision D12): they say what happened to the network, never who "won". */
export const OUTCOME_LABEL: Record<Outcome, string> = {
  attack: "La red perdió el umbral de demanda",
  defense: "La defensa contuvo la intrusión y reparó todo",
  undecided: "Sin desenlace al terminar el horizonte",
};
export const DEFENSES: [Defense, string][] = [["A", "A · Reactiva"], ["B", "B · Preventiva"], ["C", "C · Adaptativa"], ["llm", "Comandante IA"]];
export const defenseName = (d: Defense) => DEFENSES.find(([k]) => k === d)?.[1] ?? d;

type Unit = "ciclos" | "prob" | "share" | "count" | "seed";
export interface FieldSpec { key: string; label: string; unit: Unit }
/** The scenario fields, in this order, with their Spanish label and unit; values and bounds come from the catalog. */
export const FIELDS: FieldSpec[] = [
  { key: "strike_delay", label: "De comprometida a afectada", unit: "ciclos" },
  { key: "spread_cooldown", label: "Espera entre saltos", unit: "ciclos" },
  { key: "spread_p", label: "Probabilidad de salto a un vecino", unit: "prob" },
  { key: "isolation_p", label: "La segmentación frena el salto", unit: "prob" },
  { key: "eradicate_p", label: "La limpieza erradica la intrusión", unit: "prob" },
  { key: "clean_after_segmented", label: "Segmentación necesaria para limpiar", unit: "ciclos" },
  { key: "generation_share", label: "Generación que sale al afectar un área", unit: "share" },
  { key: "attack_win_lost_share", label: "Demanda sin suministro que cierra el escenario", unit: "share" },
];
/** Field crews and the seed: not scenario parameters, but they go in the same form. */
export const CREWS: FieldSpec = { key: "field_crews", label: "Cuadrillas de terreno", unit: "count" };
export const SEED: FieldSpec = { key: "seed", label: "Semilla (vacía: al azar)", unit: "seed" };
export const CREW_BOUNDS: [number, number] = [0, 60];

/** Unit shown next to an input. */
export const unitText = (u: Unit) => (u === "ciclos" ? "ciclos" : u === "prob" || u === "share" ? "%" : "");

/** Display value of a parameter (probabilities and shares as %, cycles as is) and the inverse. */
export const shown = (unit: string, v: number) => (unit === "ciclos" || unit === "count" || unit === "seed" ? v : Math.round(v * 1000) / 10);
export const stored = (unit: string, v: number) => (unit === "ciclos" || unit === "count" || unit === "seed" ? v : v / 100);

/** A number as the form shows it (es-CL: decimal comma, no thousands separator). */
export const fieldText = (unit: string, v: number) => String(shown(unit, v)).replace(".", ",");

/** Bounds of a field in its display unit. */
export function displayBounds(spec: FieldSpec, cat: CyberCatalog): [number, number] {
  if (spec.unit === "count") return CREW_BOUNDS;
  const [lo, hi] = cat.bounds[spec.key] ?? [0, 0];
  return [shown(spec.unit, lo), shown(spec.unit, hi)];
}

/** The message next to a field whose value is not valid: "Espera entre saltos: entre 1 y 12 ciclos". */
export function boundsText(spec: FieldSpec, lo: number, hi: number): string {
  const n = (x: number) => x.toLocaleString("es-CL");
  if (spec.unit === "seed") return `${spec.label.replace(/ \(.*\)$/, "")}: un número entero desde 0, o vacía`;
  const unit = spec.unit === "ciclos" ? " ciclos" : spec.unit === "count" ? "" : " %";
  const whole = spec.unit === "ciclos" || spec.unit === "count" ? ", sin decimales" : "";
  return `${spec.label}: entre ${n(lo)} y ${n(hi)}${unit}${whole}`;
}

/**
 * Reads what the user typed in a field (comma or dot as decimal separator). Returns the stored value, `null` for an
 * empty seed, or an error text. Cycles, crews and the seed are whole numbers.
 */
export function parseField(spec: FieldSpec, text: string, cat: CyberCatalog): { value: number | null; error: string | null } {
  const raw = text.trim().replace(",", ".");
  const [lo, hi] = spec.unit === "seed" ? [0, Number.MAX_SAFE_INTEGER] : displayBounds(spec, cat);
  const bad = { value: null, error: boundsText(spec, lo, hi) };
  if (raw === "") return spec.unit === "seed" ? { value: null, error: null } : bad;
  if (!/^-?\d+(\.\d+)?$/.test(raw)) return bad;
  const v = Number(raw);
  const whole = spec.unit === "ciclos" || spec.unit === "count" || spec.unit === "seed";
  if (!Number.isFinite(v) || v < lo || v > hi || (whole && !Number.isInteger(v))) return bad;
  return { value: stored(spec.unit, v), error: null };
}

/** Every field of the form, in display order. */
export const formFields = (cat: CyberCatalog): FieldSpec[] => [...FIELDS.filter((f) => f.key in cat.bounds), CREWS, SEED];

/** The initial texts of the form: the catalog defaults, crews from the catalog, an empty seed. */
export function defaultTexts(cat: CyberCatalog): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of FIELDS) if (f.key in cat.defaults) out[f.key] = fieldText(f.unit, cat.defaults[f.key]);
  out[CREWS.key] = String(cat.crews_default ?? 9);
  out[SEED.key] = "";
  return out;
}

/** Parses the whole form: the values to send, or the errors per field (key -> message). */
export function readForm(cat: CyberCatalog, texts: Record<string, string>) {
  const params: Record<string, number> = {};
  const errors: Record<string, string> = {};
  let crews = cat.crews_default ?? 9;
  let seed: number | null = null;
  for (const f of formFields(cat)) {
    const { value, error } = parseField(f, texts[f.key] ?? "", cat);
    if (error) { errors[f.key] = error; continue; }
    if (f === CREWS) crews = value ?? crews;
    else if (f === SEED) seed = value;
    else if (value != null) params[f.key] = value;
  }
  return { params, crews, seed, errors };
}

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

const MODEL_TIP = "Valor del modelo para este escenario hipotético, no una predicción.";
/** The four figures of a cycle, in a 2 by 2 grid, each with its tip; busy crews go in a line of their own. */
export function frameFigures(f: CyberFrame) {
  const active = (f.counts.compromised ?? 0) + (f.counts.struck ?? 0);
  return [
    { label: "áreas con intrusión", value: int(active), tip: `${MODEL_TIP} Áreas comprometidas o afectadas en este ciclo.` },
    { label: "áreas recuperadas", value: int(f.counts.eradicated ?? 0), tip: `${MODEL_TIP} Áreas donde la defensa erradicó la intrusión.` },
    { label: "demanda sin suministro", value: pct(f.lost_share), tip: `${MODEL_TIP} Parte de la demanda del país que la cascada dejó sin suministro.` },
    { label: "personas sin suministro", value: int(f.people_without_power), tip: `${MODEL_TIP} Personas de las comunas sin suministro en la red reducida.` },
  ];
}

/** Area order for the result: affected first, then compromised, recovered and healthy; the catalog order inside each. */
const STATE_ORDER: Record<AreaState, number> = { struck: 0, compromised: 1, eradicated: 2, clean: 3 };
export function areaOrder<T extends { id: string }>(areas: T[], states: Record<string, AreaState>): T[] {
  return areas.map((a, i) => ({ a, i })).sort((x, y) => STATE_ORDER[states[x.a.id] ?? "clean"] - STATE_ORDER[states[y.a.id] ?? "clean"] || x.i - y.i).map((x) => x.a);
}
