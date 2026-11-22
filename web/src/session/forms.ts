/**
 * Field rules of the Datos forms and the numbers they show (docs/mapa3.md section 11). The bounds repeat the API's
 * (`api/session_schemas.py`): a value the API would refuse is caught next to its field, in Spanish, before sending.
 */
export type FieldType = "text" | "number" | "kv" | "tech" | "kind";
export interface Rule {
  required?: boolean;
  /** Smallest value; `gt` makes it exclusive (MW must be more than 0). */
  min?: number; gt?: boolean; max?: number;
  /** Bus id field (B### of the network). */
  bus?: boolean;
  maxLength?: number;
}
export interface Spec extends Rule { key: string; label: string; type?: FieldType }

const n = (x: number) => x.toLocaleString("es-CL");
/** The rule of a field as a short Spanish text: "entre -56 y -17", "más de 0 y hasta 3.000". */
function range(r: Rule): string {
  const lo = r.min == null ? null : r.gt ? `más de ${n(r.min)}` : `desde ${n(r.min)}`;
  if (r.min != null && r.max != null && !r.gt) return `entre ${n(r.min)} y ${n(r.max)}`;
  if (lo && r.max != null) return `${lo} y hasta ${n(r.max)}`;
  return lo ?? (r.max != null ? `hasta ${n(r.max)}` : "");
}

/** Parses a number typed with a decimal comma or dot; NaN when it is not a plain number. */
export function parseNumber(raw: string): number {
  const t = raw.trim().replace(",", ".");
  return /^-?\d+(\.\d+)?$/.test(t) ? Number(t) : Number.NaN;
}

/** The error of one field, or null when its value is acceptable. An empty optional field is acceptable. */
export function fieldError(spec: Spec, raw: string): string | null {
  const v = raw.trim();
  if (v === "") return spec.required ? "Obligatorio." : null;
  if (spec.type === "number" || spec.type === "kv") {
    const x = parseNumber(v);
    if (!Number.isFinite(x)) return "Escribe un número (por ejemplo 2,5).";
    if ((spec.min != null && (spec.gt ? x <= spec.min : x < spec.min)) || (spec.max != null && x > spec.max)) return `Debe ser ${range(spec)}.`;
    return null;
  }
  if (spec.bus && !/^B\d{3}$/.test(v)) return "Escribe el id de una barra, como B010.";
  if (spec.maxLength != null && v.length > spec.maxLength) return `Máximo ${spec.maxLength} caracteres.`;
  return null;
}

/** Errors of a whole form, by field key; empty when it can be sent. */
export function formErrors(specs: Spec[], values: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const s of specs) {
    const e = fieldError(s, values[s.key] ?? "");
    if (e) out[s.key] = e;
  }
  return out;
}

/** MW as the Datos lists show them: whole above 100, one decimal below, decimal comma ("2,5 MW" stays 2,5). */
export const mwText = (x: number) => x.toLocaleString("es-CL", { maximumFractionDigits: Math.abs(x) >= 100 ? 0 : 1 });

/** A line loading as a percent with one decimal, so 100,4 % does not read as "100 %" next to an overload count. */
export const loadingText = (share: number) => `${(share * 100).toLocaleString("es-CL", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`;

/** API bounds (`api/session_schemas.py`): continental Chile, element MW in (0, 3000], line capacity in (0, 5000], x in (0, 1]. */
export const LAT: Rule = { min: -56, max: -17 };
export const LON: Rule = { min: -76, max: -66 };
export const ELEMENT_MW: Rule = { min: 0, gt: true, max: 3000 };
export const BUS_MW: Rule = { min: 0, max: 20000 };
export const CAPACITY_MW: Rule = { min: 0, gt: true, max: 5000 };
export const X_PU: Rule = { min: 0, gt: true, max: 1 };
export const NAME: Rule = { maxLength: 80 };
