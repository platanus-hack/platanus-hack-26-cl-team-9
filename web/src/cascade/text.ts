import type { Event, Network } from "./types";

const ZONES: Record<string, string> = { centro_sur: "Centro-sur", norte_grande: "Norte Grande" };
const REASONS: Record<string, string> = {
  no_generation: "queda sin generación", no_load: "queda sin demanda y su generación se desconecta",
  no_inertia: "no tiene inercia sincrónica", frequency: "la frecuencia cae bajo 47,5 Hz",
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

/** Why: every sentence is built from fixed templates, so the narration is reproducible and carries no model text. */
export function narrate(event: Event, network: Network): string {
  const p = event.params;
  const names = event.ids.map((id) => lineName(network, id)).join(" y ");
  switch (event.text_key) {
    case "line_cut": return `Sale de servicio la línea ${names}.`;
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

export const int = (n: number) => Math.round(n).toLocaleString("es-CL");
export const mw = (n: unknown) => int(Number(n ?? 0));
export const hz = (n: number) => n.toLocaleString("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const secs = (n: number) => n.toLocaleString("es-CL", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
export const pct = (n: number) => `${Math.round(n * 100)} %`;

export function formatPeople(n: number): string {
  return n >= 1e6 ? `${(n / 1e6).toLocaleString("es-CL", { maximumFractionDigits: 1 })} M` : int(n);
}

const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

/** Wall clock of the operating point (snapshot "YYYY-MM-DD HH:MM") plus t seconds of simulation. */
export function clock(snapshot: string | undefined, t: number) {
  const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})/.exec(snapshot ?? "");
  if (!m) return { date: "", hms: "--:--:--", tenths: "--:--:--,-", zone: "" };
  const [, y, mo, d, h, mi] = m.map(Number);
  const total = h * 3600 + mi * 60 + t;
  const pad = (x: number) => String(Math.floor(x)).padStart(2, "0");
  const hms = `${pad(total / 3600 % 24)}:${pad((total % 3600) / 60)}:${pad(total % 60)}`;
  // Continental Chile keeps summer time (GMT-3) from September to early April.
  const zone = mo >= 9 || mo <= 3 ? "GMT-3" : "GMT-4";
  return { date: `${d} ${MONTHS[mo - 1]} ${y}`, hms, tenths: `${hms},${Math.floor(t * 10 + 1e-6) % 10}`, zone };
}
