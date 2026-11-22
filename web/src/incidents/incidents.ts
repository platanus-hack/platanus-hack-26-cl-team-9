import { int, pct, usdM } from "../cascade/text";
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
export const LEVELS: Record<string, string> = { L0: "Absorbido", L1: "Contenido", L2: "Apagón regional", L3: "Apagón nacional" };
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
// Macro zones of the theatre (backend/src/cascadasen/domain/unify.py, MACRO_ZONES).
const ZONES: Record<string, string> = { NG: "Norte Grande", NC: "Norte Chico", CE: "Centro", CS: "Centro-Sur", SU: "Sur" };
const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const MONTH_IDS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
/** Operating area id -> name, from `GET /sim/catalog` (`cyber_attack.areas`); empty until it arrives. */
export type AreaNames = Record<string, string>;
/**
 * Sources whose catalog label is a repository file (the 25F reference cites `docs/idea.md [3]`), named for people with
 * the URL that docs/datasets.md gives for that reference.
 */
const KNOWN_SOURCES: Record<string, IncidentSource> = {
  "docs/idea.md": { label: "Informe del Coordinador Eléctrico Nacional sobre el 25F", url: "https://www.coordinador.cl/wp-content/uploads/2025/03/2025-03-19-RESUMEN-EJECUTIVO.pdf" },
};

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

/**
 * Operating point id ("nov2026-1300") as Spanish text ("13:00 del 1 nov 2026"). A point is the representative snapshot
 * of its month, taken on the 1st (`snapshot` in `cache/index.json`).
 */
export function pointText(point: string): string {
  const m = /^([a-z]{3})(\d{4})-(\d{2})(\d{2})$/.exec(point);
  if (!m) return point;
  const mo = MONTH_IDS.indexOf(m[1]);
  return `${m[3]}:${m[4]} del 1 ${mo >= 0 ? MONTHS[mo] : m[1]} ${m[2]}`;
}

/** ISO date ("2026-08-26") as "26 ago 2026"; anything else is returned as it came. */
export function dateText(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  return m ? `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}` : iso;
}

/**
 * A place code of the theatre in words: an area ("A01") by its name, a corridor ("A06-A07") as the corridor between two
 * areas, a macro zone ("NC") by its name. Unknown codes stay as they are.
 */
export function placeText(code: string, areas: AreaNames = {}): string {
  const pair = /^(A\d+)-(A\d+)$/.exec(code);
  if (pair) return areas[pair[1]] && areas[pair[2]] ? `el corredor entre ${areas[pair[1]]} y ${areas[pair[2]]}` : `el corredor ${code}`;
  if (/^A\d+$/.test(code)) return areas[code] ?? `el área ${code}`;
  return ZONES[code] ? `la zona ${ZONES[code]}` : code;
}

/**
 * Backend text made readable (D11): area, corridor and zone codes by name, `edac:centro_sur` as "EDAC Centro-Sur",
 * bracket reference numbers ("[44]") and repository file names removed.
 */
export function plainText(text: string, areas: AreaNames = {}): string {
  return text
    .replace(/\bedac:([a-z_]+)/g, (_, z: string) => `EDAC ${z === "centro_sur" ? "Centro-Sur" : z.split("_").map((w) => w[0].toUpperCase() + w.slice(1)).join(" ")}`)
    .replace(/\b(A\d{2}-A\d{2}|A\d{2})\b/g, (code) => placeText(code, areas))
    .replace(/\b(en|de|a) (NG|NC|CE|CS|SU)\b/g, (_, prep: string, z: string) => `${prep} ${placeText(z)}`)
    .replace(/ en [\w./-]+\.(geojson|json|csv|yaml|md)\b/g, " en los datos del modelo")
    .replace(/\bEstado de la red\b/g, "la pestaña Cambios")
    .replace(/\s*\[\d+\]/g, "");
}

/** A catalog source as people read it: repository files become the document they cite, with its public URL. */
export function sourceOf(s: IncidentSource): IncidentSource {
  return KNOWN_SOURCES[s.url] ?? s;
}

/** One effect of the scenario in Spanish: event, place and size, never how it was caused. */
export function effectText(e: IncidentEffect, areas: AreaNames = {}): string {
  const what = EVENT_LABELS[e.type] ?? e.type;
  const where = placeText(e.target, areas);
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
/** True when a cascade has something to show on the map: load shed, a dark bus or an opened line. */
export const visible = (tl: Timeline) => (tl.summary?.load_shed_mw ?? 0) > 0 || (tl.summary?.dark_buses ?? 0) > 0 || (tl.summary?.lines_opened?.length ?? 0) > 0;

/** Minutes per theatre cycle, read from the snapshots (t_min / cycle); 5 min when there is none to read. */
export function cycleMinutes(snapshots: RunSnapshot[]): number {
  const s = snapshots.find((x) => x.cycle > 0 && x.t_min > 0);
  return s ? s.t_min / s.cycle : DEFAULT_CYCLE_MIN;
}

export interface Figure { label: string; value: string; tip: string; text?: boolean }
const hoursText = (h: number) => `${h.toLocaleString("es-CL", { maximumFractionDigits: 2 })} h`;
/** The outage hours of a card in words: calibrated with the 25F or an assumption. */
export function outageText(card: IncidentCard): string {
  const h = card.outage_duration_h;
  return `${hoursText(h.value)} ${h.is_assumption ? "(supuesto)" : "(calibrado con el 25F)"}`;
}
/** Card figures as text, each with where it comes from. MWh and cost are the cascade engine's own, the same as
 * the Cambios tab: dark demand pays a black start, load shed in a surviving island pays about an hour (assumption). */
export function cardFigures(card: IncidentCard): Figure[] {
  const blackout = card.cost_basis?.blackout_restoration_h?.value ?? 7.34;
  const shed = card.cost_basis?.shed_restoration_h?.value ?? 1;
  return [
    { label: "personas sin suministro", value: int(card.people_without_power), tip: "Máximo de la corrida en la red reducida. Valor del modelo, no una predicción." },
    { label: "MW de carga perdida", value: int(card.load_shed_mw), tip: "Potencia no servida máxima de la corrida. Valor del modelo." },
    { label: "MWh no servidos", value: int(card.unserved_energy_mwh), tip: `Del motor de cascadas, el mismo cálculo de la pestaña de cambios: interrupción de ${outageText(card)}.` },
    { label: "costo de falla", value: usdM(card.failure_cost_usd), tip: `Costo de falla de la Comisión Nacional de Energía (8,79 US$/kWh): la carga apagada paga ${blackout.toLocaleString("es-CL")} h de arranque en negro, calibradas con el 25F, y un recargo por apagón total; el corte de carga paga ${shed.toLocaleString("es-CL")} h (supuesto). Una valoración para planificar, no una pérdida medida.` },
  ];
}

/** Agentic-response figures from `report.indicators`, all experimental. A result in words is marked `text`. */
export function responseFigures(ind: Indicators, minutesPerCycle: number): Figure[] {
  const tip = "Indicador experimental de los agentes defensivos simulados. Valor del modelo.";
  const ttu = ind.situational_awareness?.time_to_understanding_cycles;
  const understood = ind.situational_awareness?.understood !== false && ttu != null;
  const out: Figure[] = [
    understood
      ? { label: "tiempo hasta entender", value: `${int(ttu!)} ciclos · ${int(ttu! * minutesPerCycle)} min`, tip }
      : { label: "tiempo hasta entender", value: "no se identificó en el horizonte", tip, text: true },
  ];
  if (ind.mission_continuity != null) out.push({ label: "continuidad de misión", value: pct(ind.mission_continuity), tip });
  if (ind.wrong_decisions != null) out.push({ label: "decisiones innecesarias", value: int(ind.wrong_decisions), tip });
  if (ind.operational_reserve?.final != null) out.push({ label: "reserva final", value: pct(ind.operational_reserve.final), tip });
  return out;
}

/** The incident had no effect on supply: level L0 and nobody without supply. */
export const absorbed = (card: IncidentCard) => card.consequence_level === "L0" && card.people_without_power <= 0 && card.load_shed_mw <= 0;

/** Spanish text of a failed call: `status` is null when the backend could not be reached at all. */
export function incidentError(status: number | null, message: string, retryAfter: number | null = null): string {
  if (status === null) return "No se pudo conectar con el servidor.";
  if (status === 429) return `Demasiadas solicitudes a la sesión; espera ${retryAfter ? `${retryAfter} s` : "un momento"} y vuelve a intentarlo.`;
  if (status === 503) return "El servidor no puede simular ahora. Intenta de nuevo más tarde.";
  if (status === 422) return `El servidor rechazó el escenario: ${message}`;
  return message || "No se pudo completar la simulación.";
}

/** Rows of the Ciclos list: `after_action.timeline`, plus any cycle with a cascade that has no line there, in order. */
export function cycleRows(timeline: AarCycle[], cascades: CascadeCycle[]): AarCycle[] {
  const have = new Set(timeline.map((r) => r.cycle));
  const extra = cascades.filter((c) => !have.has(c.cycle)).map((c) => ({ cycle: c.cycle, t_min: c.t_min, lines: [] }));
  return [...timeline, ...extra].sort((a, b) => a.cycle - b.cycle);
}
