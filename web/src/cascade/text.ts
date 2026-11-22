import { fmt } from "../lib/format";
import type { Event, Network } from "./types";

const ZONES: Record<string, string> = { centro_sur: "Centro-sur", norte_grande: "Norte Grande" };
const REASONS: Record<string, string> = {
  no_generation: "queda sin generación", no_load: "queda sin demanda y su generación se desconecta",
  no_inertia: "no tiene inercia sincrónica", frequency: "la frecuencia cae bajo 47,5 Hz",
  voltage: "colapsa por tensión al separarse el corredor del 25F con un flujo previo fuera del rango del esquema de defensa",
};

export const zoneName = (zone: string) => ZONES[zone] ?? zone;

const SMALL_WORDS = new Set(["de", "del", "la", "las", "los", "el", "y", "e", "a"]);

/** "S/E CERRO NAVIA (TRANSELEC)" -> "Cerro Navia (TRANSELEC)". Owner names in parentheses and codes stay as written. */
export function placeName(raw: string): string {
  const name = raw.replace(/^S\/E /, "");
  const paren = name.indexOf("(");
  const head = paren >= 0 ? name.slice(0, paren) : name;
  const words = head.split(/(\s+)/).map((w, i) => {
    if (!/^[A-ZÁÉÍÓÚÑ]+$/.test(w) || /^[IVX]+$/.test(w)) return w; // codes, digits, roman numerals
    const lower = w.toLowerCase();
    return i > 0 && SMALL_WORDS.has(lower) ? lower : lower[0].toUpperCase() + lower.slice(1);
  });
  return words.join("") + (paren >= 0 ? name.slice(paren) : "");
}

export function lineName(network: Network, id: string): string {
  const line = network.lines.find((l) => l.id === id);
  const node = (nid: string) => { const n = network.nodes.find((x) => x.id === nid); return n ? placeName(n.name) : nid; };
  return line ? `${node(line.a)} – ${node(line.b)} (${Math.round(line.kv)} kV)` : id;
}

/** Prefix of a substation shutdown scenario: `sub-B012` opens every line of B012 at t = 0 (cache `<point>/sub-B012.json`). */
export const SUBSTATION_PREFIX = "sub-";

/** The substation behind a scenario id, or null when the id is a line. */
export const shutdownNode = (id: string): string | null => (id.startsWith(SUBSTATION_PREFIX) ? id.slice(SUBSTATION_PREFIX.length) : null);

/** Ids of the lines with one end at the substation. */
export function substationLines(network: Network, nodeId: string): string[] {
  return network.lines.filter((l) => l.a === nodeId || l.b === nodeId).map((l) => l.id);
}

/** Name of a scenario cut: "Subestación Cerro Navia" for `sub-B###`, the line name otherwise. */
export function cutName(network: Network, id: string): string {
  const node = shutdownNode(id);
  if (!node) return lineName(network, id);
  const n = network.nodes.find((x) => x.id === node);
  return `Subestación ${n ? placeName(n.name) : node}`;
}

/** "A", "A y B", "A, B y C". */
const listEs = (items: string[]) => (items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} y ${items[items.length - 1]}`);

/** Why: every sentence is built from fixed templates, so the narration is reproducible and carries no model text. */
export function narrate(event: Event, network: Network): string {
  const p = event.params;
  const names = event.ids.map((id) => lineName(network, id)).join(" y ");
  switch (event.text_key) {
    case "line_cut": return event.ids.length > 1
      ? `Salen de servicio las líneas ${listEs(event.ids.map((id) => lineName(network, id)))}.`
      : `Sale de servicio la línea ${names}.`;
    case "line_overload_open": return `${names} supera el 120 % de su capacidad y sale de servicio.`;
    case "island_formed": return `Se forma una isla de ${p.buses} subestaciones: ${mw(p.gen_mw)} MW de generación para ${mw(p.load_mw)} MW de demanda.`;
    case "load_shed": return `Corte automático de carga en ${zoneName(String(p.zone))}, escalón ${p.step}: ${mw(p.mw)} MW.`;
    case "island_blackout": return `Se apaga una isla de ${p.buses} subestaciones (${mw(p.load_mw)} MW): ${REASONS[String(p.reason)] ?? p.reason}.`;
    case "island_stable": return `La isla se estabiliza en ${hz(Number(p.final_hz ?? p.min_hz))} Hz.`;
    default: return event.text_key;
  }
}

/** Short title for the map callout: the history row's wording up to the first colon or sentence end ("7.872" stays). */
export const shortTitle = (s: string) => s.replace(/(: |\. |\.$).*$/, "");

export const int = fmt;
export const mw = (n: unknown) => int(Number(n ?? 0));
export const hz = (n: number) => n.toLocaleString("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const secs = (n: number) => n.toLocaleString("es-CL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
export const pct = (n: number) => `${Math.round(n * 100)} %`;
/** US$ in millions with one decimal, Chilean format: 69335520 -> "US$ 69,3 M". */
export const usdM = (n: number) => `US$ ${(n / 1e6).toLocaleString("es-CL", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} M`;
/** Health index on its 0-1 scale with two decimals: "0,67". */
export const index2 = (n: number) => n.toLocaleString("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export function formatPeople(n: number): string {
  return n >= 1e6 ? `${(n / 1e6).toLocaleString("es-CL", { maximumFractionDigits: 1 })} M` : int(n);
}

const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const pad = (x: number) => String(Math.floor(x)).padStart(2, "0");

/** Snapshot "YYYY-MM-DD HH:MM" of an operating point as numbers, or null when it does not parse. */
function parseSnapshot(snapshot: string | undefined) {
  const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/.exec(snapshot ?? "");
  if (!m) return null;
  const [, y, mo, d, h, mi] = m.map(Number);
  return { y, mo, d, h, mi };
}

/** Wall clock of the operating point plus t seconds of simulation, for the timeline card. */
export function clock(snapshot: string | undefined, t: number) {
  const s = parseSnapshot(snapshot);
  if (!s) return { hms: "--:--:--", tenths: "--:--:--,-" };
  const total = s.h * 3600 + s.mi * 60 + t;
  const hms = `${pad(total / 3600 % 24)}:${pad((total % 3600) / 60)}:${pad(total % 60)}`;
  return { hms, tenths: `${hms},${Math.floor(t * 10 + 1e-6) % 10}` };
}

/** Date line of an operating condition in the rail: "1 nov 2026 · 13:00". */
export function conditionDate(snapshot: string | undefined): string {
  const s = parseSnapshot(snapshot);
  return s ? `${s.d} ${MONTHS[s.mo - 1]} ${s.y} · ${pad(s.h)}:${pad(s.mi)}` : "";
}

/**
 * Short name of an operating condition, from the parenthetical of its label: "Noviembre 2026, 13:00 (mediodía solar)"
 * -> "Mediodía solar"; "(referencia del 25F)" -> "Referencia 25F". Labels without one are returned whole.
 */
export function conditionName(label: string): string {
  const m = /\(([^)]+)\)\s*$/.exec(label);
  if (!m) return label;
  const name = m[1].trim().replace(/^referencia del /i, "referencia ");
  return name ? name[0].toUpperCase() + name.slice(1) : label;
}
