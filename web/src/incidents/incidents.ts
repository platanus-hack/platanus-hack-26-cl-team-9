import { int, pct, usdM, zoneName } from "../cascade/text";
import type { Assumed, Timeline } from "../cascade/types";

/**
 * Documented-incident scenarios in the web (docs/attack-sim.md section 3.1, docs/mapa3.md section 4.2): types of the
 * catalog, the consequence card and the after-action, and the pure decisions of the Incidentes view. Only the effect
 * is modelled, never the technique (docs/cyber.md section 8); the catalog keeps the order of its file.
 */
export type Policy = "A" | "B" | "C";
export interface IncidentSource { label: string; url: string }
export interface IncidentEffect { cycle: number; type: string; target: string; params: Record<string, unknown> }
export interface IncidentInfo {
  id: string; title: string; date: string; kind: "cyber_documented" | "reference_not_cyber" | string; verified: boolean;
  sources: IncidentSource[]; notes: string[]; mitigations: string[]; operating_point: string; horizon: number; effects: IncidentEffect[];
}
export interface IncidentCatalog { notices: string[]; default_duration_h: Assumed; incidents: IncidentInfo[] }
/** `report.incident.consequence_card`. */
export interface IncidentCard {
  incident: string; consequence_level: string; people_without_power: number; load_shed_mw: number;
  unserved_energy_mwh: number; failure_cost_usd: number; outage_duration_h: Assumed; note: string; notices: string[];
}
/** `after_action.incident`. */
export interface IncidentAar {
  title: string; summary: string; effect: string; prevention: string[]; notes: string[]; sources: IncidentSource[]; verified: boolean; notices: string[];
}
/** One row of `after_action.timeline`: the events and actions of a cycle, already in Spanish. */
export interface AarCycle { cycle: number; t_min: number; lines: string[] }
/** The part of `report.indicators` the view shows (experimental indicators, docs/strategy.md). */
export interface Indicators {
  experimental?: boolean; mission_continuity?: number; wrong_decisions?: number;
  situational_awareness?: { time_to_understanding_cycles?: number | null; understood?: boolean; onset_cycle?: number | null };
  operational_reserve?: { final?: number; minimum?: number };
}
/** A snapshot of the run as `POST .../step` returns it; only the fields this view reads. */
export interface RunSnapshot { cycle: number; t_min: number; transient?: Timeline | null }
export interface CascadeCycle { cycle: number; t_min: number; timeline: Timeline }

export const NOTICES = [
  "Escenario hipotético: se modela el efecto, no el ataque.",
  "Consecuencia simulada en una red reducida, no una predicción.",
];
export const LEVELS: Record<string, string> = { L0: "L0 · absorbido", L1: "L1 · contenido", L2: "L2 · apagón regional", L3: "L3 · apagón nacional" };
export const POLICIES: [Policy, string, string][] = [["A", "A", "Reactiva"], ["B", "B", "Preventiva"], ["C", "C", "Adaptativa"]];
export const MIN_DURATION_H = 0.25;
export const MAX_DURATION_H = 720;
const DEFAULT_CYCLE_MIN = 5;
// Same labels as backend/src/cascadasen/domain/theater/params/narrative_es.yaml (event_types).
const EVENT_LABELS: Record<string, string> = {
  C1_generation_loss: "Pérdida de generación",
  C2_common_mode_loss: "Pérdida simultánea por zona y tecnología",
  C3_transmission_opening: "Apertura de transmisión",
  C5_remote_dispatch_loss: "Pérdida de despacho remoto",
  D4_comms_loss: "Pérdida de comunicaciones",
};
const TECH: Record<string, string> = { solar: "solar", eolica: "eólica", hidro: "hidráulica", termica: "térmica" };

/** What to do with the session before launching: the incident runs at its own hour (422 otherwise). */
export type SessionPlan = "reuse" | "create" | "replace";
export function sessionPlan(sessionPoint: string | null | undefined, incident: Pick<IncidentInfo, "operating_point">): SessionPlan {
  if (!sessionPoint) return "create";
  return sessionPoint === incident.operating_point ? "reuse" : "replace";
}

/** "kind" label of a catalog card: a reference that is not cyber, or an unverified (press-based) incident. */
export function incidentTag(inc: Pick<IncidentInfo, "kind" | "verified">): string | null {
  if (inc.kind === "reference_not_cyber") return "referencia, no es ciber";
  return inc.verified ? null : "no verificado";
}

/** Operating point id ("nov2026-1300") as Spanish text ("nov. 2026, 13:00"). */
export function pointText(point: string): string {
  const m = /^([a-z]{3})(\d{4})-(\d{2})(\d{2})$/.exec(point);
  return m ? `${m[1]}. ${m[2]}, ${m[3]}:${m[4]}` : point;
}

/** One effect of the scenario in Spanish: event, place and size, never how it was caused. */
export function effectText(e: IncidentEffect): string {
  const what = EVENT_LABELS[e.type] ?? e.type;
  const where = /^A\d+-A\d+$/.test(e.target) ? `corredor ${e.target}` : /^A\d+$/.test(e.target) ? `área ${e.target}` : zoneName(e.target);
  const size = [
    typeof e.params.mw === "number" ? `${int(e.params.mw)} MW` : null,
    typeof e.params.share === "number" ? `${pct(e.params.share)}${typeof e.params.tech === "string" ? ` de la ${TECH[e.params.tech] ?? e.params.tech}` : ""}` : null,
  ].filter(Boolean).join(", ");
  return `Ciclo ${e.cycle}: ${what} en ${where}${size ? ` (${size})` : ""}`;
}

/** Cycles whose snapshot carries a cascade (`transient`, the same shape as a cut's Timeline), in cycle order. */
export function cascadeCycles(snapshots: RunSnapshot[]): CascadeCycle[] {
  return snapshots.filter((s) => s.transient && s.transient.frames?.length).map((s) => ({ cycle: s.cycle, t_min: s.t_min, timeline: s.transient! }));
}

/** Minutes per theatre cycle, read from the snapshots (t_min / cycle); 5 min when there is none to read. */
export function cycleMinutes(snapshots: RunSnapshot[]): number {
  const s = snapshots.find((x) => x.cycle > 0 && x.t_min > 0);
  return s ? s.t_min / s.cycle : DEFAULT_CYCLE_MIN;
}

export interface Figure { label: string; value: string; tip: string }
/** Card figures as text, each with where it comes from; duration, MWh and cost are flagged as assumptions. */
export function cardFigures(card: IncidentCard): Figure[] {
  const h = card.outage_duration_h.value;
  const hours = `${h.toLocaleString("es-CL", { maximumFractionDigits: 2 })} h`;
  const assumed = card.outage_duration_h.is_assumption ? `${hours} supuestas (editable)` : hours;
  return [
    { label: "personas sin luz", value: int(card.people_without_power), tip: "Máximo de la corrida en la red reducida (report.incident.consequence_card)." },
    { label: "MW no servidos", value: int(card.load_shed_mw), tip: "Potencia no servida máxima de la corrida (report.incident.consequence_card)." },
    { label: "MWh no servidos", value: int(card.unserved_energy_mwh), tip: `Supuesto: la potencia no servida máxima durante ${assumed}.` },
    { label: "costo de falla", value: usdM(card.failure_cost_usd), tip: `Supuesto: ${assumed} por el costo de falla regulatorio de la CNE [19]; una valoración para planificar, no una pérdida medida.` },
  ];
}

/** Agentic-response figures from `report.indicators`, all experimental. */
export function responseFigures(ind: Indicators, minutesPerCycle: number): Figure[] {
  const tip = "Indicador experimental del teatro estratégico (report.indicators; docs/strategy.md).";
  const ttu = ind.situational_awareness?.time_to_understanding_cycles;
  const understood = ind.situational_awareness?.understood !== false && ttu != null;
  const out: Figure[] = [
    { label: "tiempo hasta entender", value: understood ? `${int(ttu!)} ciclos · ${int(ttu! * minutesPerCycle)} min` : "no llegó a entender", tip },
  ];
  if (ind.mission_continuity != null) out.push({ label: "continuidad de misión", value: pct(ind.mission_continuity), tip });
  if (ind.wrong_decisions != null) out.push({ label: "decisiones innecesarias", value: int(ind.wrong_decisions), tip });
  if (ind.operational_reserve?.final != null) out.push({ label: "reserva final", value: pct(ind.operational_reserve.final), tip });
  return out;
}

/** Duration typed by the user, clamped to what the API accepts; null when it is not a number. */
export function parseDuration(text: string): number | null {
  const n = Number(text.replace(",", "."));
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.min(MAX_DURATION_H, Math.max(MIN_DURATION_H, n));
}
