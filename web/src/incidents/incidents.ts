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
/** A calibrated cost term with where it comes from (`cascade.yaml` `cost`): a source or `is_assumption`. */
export interface CostTerm { value: number; source: string | null; is_assumption: boolean }
export interface IncidentCatalog { notices: string[]; cost_basis: Record<string, CostTerm>; incidents: IncidentInfo[] }
/** `report.incident.consequence_card`. */
export interface IncidentCard {
  incident: string; consequence_level: string; people_without_power: number; load_shed_mw: number;
  unserved_energy_mwh: number; failure_cost_usd: number; cost_per_hour_usd: number; outage_duration_h: Assumed;
  cost_breakdown: Record<string, number>; cost_basis: Record<string, CostTerm>; note: string; notices: string[];
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

/**
 * Cycles whose snapshot carries a visible cascade (`transient`, the same shape as a cut's Timeline), in cycle order. A
 * transient that only formed a stable island, with no line opened, no bus dark and no load shed, has nothing to show.
 */
export function cascadeCycles(snapshots: RunSnapshot[]): CascadeCycle[] {
  return snapshots.filter((s) => s.transient?.frames?.length && visible(s.transient)).map((s) => ({ cycle: s.cycle, t_min: s.t_min, timeline: s.transient! }));
}
const visible = (tl: Timeline) => (tl.summary?.load_shed_mw ?? 0) > 0 || (tl.summary?.dark_buses ?? 0) > 0 || (tl.summary?.lines_opened?.length ?? 0) > 0;

/** Minutes per theatre cycle, read from the snapshots (t_min / cycle); 5 min when there is none to read. */
export function cycleMinutes(snapshots: RunSnapshot[]): number {
  const s = snapshots.find((x) => x.cycle > 0 && x.t_min > 0);
  return s ? s.t_min / s.cycle : DEFAULT_CYCLE_MIN;
}

export interface Figure { label: string; value: string; tip: string }
/** Card figures as text, each with where it comes from. MWh and cost are the cascade engine's own, the same as
 * "Estado de la red": dark demand pays a black start, load shed in a surviving island pays about an hour (assumption). */
export function cardFigures(card: IncidentCard): Figure[] {
  const h = card.outage_duration_h;
  const hours = `${h.value.toLocaleString("es-CL", { maximumFractionDigits: 2 })} h ${h.is_assumption ? "(supuesto)" : "(calibrado con el 25F, [44])"}`;
  const blackout = card.cost_basis?.blackout_restoration_h?.value ?? 7.34;
  const shed = card.cost_basis?.shed_restoration_h?.value ?? 1;
  return [
    { label: "personas sin luz", value: int(card.people_without_power), tip: "Máximo de la corrida en la red reducida (report.incident.consequence_card)." },
    { label: "MW no servidos", value: int(card.load_shed_mw), tip: "Potencia no servida máxima de la corrida (report.incident.consequence_card)." },
    { label: "MWh no servidos", value: int(card.unserved_energy_mwh), tip: `Del motor de cascadas, igual que Estado de la red: interrupción de ${hours}.` },
    { label: "costo de falla", value: usdM(card.failure_cost_usd), tip: `Costo de falla de la CNE [19] como en Estado de la red: la carga apagada paga ${blackout.toLocaleString("es-CL")} h de arranque en negro [44] y un recargo por apagón total; el deslastre paga ${shed.toLocaleString("es-CL")} h (supuesto). Una valoración para planificar, no una pérdida medida.` },
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

/** Spanish text of a failed call: `status` is null when the backend could not be reached at all. */
export function incidentError(status: number | null, message: string, retryAfter: number | null = null): string {
  if (status === null) return `No se pudo conectar con el backend (${message}). Los incidentes necesitan el servidor; el resto del mapa sigue funcionando.`;
  if (status === 429) return `Demasiadas solicitudes a la sesión; espera ${retryAfter ? `${retryAfter} s` : "un momento"} y vuelve a intentarlo.`;
  if (status === 503) return "El servidor no puede simular ahora (503). Intenta de nuevo más tarde.";
  if (status === 422) return `El servidor rechazó el incidente: ${message}`;
  return message;
}

/** Rows of the Ciclos list: `after_action.timeline`, plus any cycle with a cascade that has no line there, in order. */
export function cycleRows(timeline: AarCycle[], cascades: CascadeCycle[]): AarCycle[] {
  const have = new Set(timeline.map((r) => r.cycle));
  const extra = cascades.filter((c) => !have.has(c.cycle)).map((c) => ({ cycle: c.cycle, t_min: c.t_min, lines: [] }));
  return [...timeline, ...extra].sort((a, b) => a.cycle - b.cycle);
}
