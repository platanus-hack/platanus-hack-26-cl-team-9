import type { Narrative, Source } from "./types";

// Fixed Spanish templates served by the backend (GET /sim/narrative, cache/theater/narrative_es.json):
// the operation mode shows no model-written text except the optional LLM narrative of the after-action.
export const NOTICE = "Escenario hipotético: se modela el efecto, no el ataque.";

export const SOURCE_LABEL: Record<Source, string> = {
  adversary: "Adversario",
  external: "Imprevisto",
  user: "Tú",
  scenario: "Escenario",
};

function section(n: Narrative | null, name: string): Record<string, string> {
  const s = n?.[name];
  return s && typeof s === "object" ? (s as Record<string, string>) : {};
}

/** Replace {name} placeholders; numbers below 1 are shown as percentages (confidence, shares). */
export function render(template: string, params: Record<string, unknown> = {}): string {
  return template.replace(/\{(\w+)\}/g, (_, k: string) => {
    const v = params[k];
    if (typeof v === "number") return v > 0 && v < 1 ? `${Math.round(v * 100)}%` : v.toLocaleString("es-CL");
    if (Array.isArray(v)) return v.join(", ");
    return v == null ? `{${k}}` : String(v);
  });
}

export function notice(n: Narrative | null): string {
  return typeof n?.notice === "string" ? n.notice : NOTICE;
}

export function eventLabel(n: Narrative | null, type: string): string {
  return section(n, "event_types")[type] ?? type;
}

export function actionText(n: Narrative | null, action: string, target: string): string {
  const t = section(n, "actions")[action];
  return t ? render(t, { target }) : `${action} en ${target}`;
}

export function label(n: Narrative | null, key: string): string {
  return section(n, "labels")[key] ?? key;
}

/** "vetoed:log_crew_too_far" -> "Vetada: Logística no envía cuadrilla…"; "invalid:area_segmented" -> "No válida: El área está aislada". */
export function decisionText(n: Narrative | null, reason: string): string {
  const [kind, code] = reason.split(":", 2);
  const head = section(n, "decisions")[kind] ?? kind;
  if (!code) return head;
  const detail = section(n, "rationale")[code] ?? section(n, "verdicts")[code] ?? code;
  return `${head}: ${detail}`;
}

export function verdictText(n: Narrative | null, code: string): string {
  return section(n, "verdicts")[code] ?? code;
}

export function rationale(n: Narrative | null, key: string, params: Record<string, unknown> = {}): string {
  const t = section(n, "rationale")[key];
  return t ? render(t, params) : key;
}

export function clock(tMin: number): string {
  const h = Math.floor(tMin / 60);
  const m = tMin % 60;
  return h ? `${h} h ${String(m).padStart(2, "0")} min` : `${m} min`;
}

export function pct(x: number, digits = 1): string {
  return `${(x * 100).toLocaleString("es-CL", { maximumFractionDigits: digits, minimumFractionDigits: digits })} %`;
}
