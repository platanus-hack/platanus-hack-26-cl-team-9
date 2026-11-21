import type { Event, Network } from "./types";

const ZONES: Record<string, string> = { centro_sur: "centro-sur", norte_grande: "Norte Grande" };
const REASONS: Record<string, string> = {
  no_generation: "queda sin generación", no_load: "queda sin demanda y su generación se desconecta",
  no_inertia: "no tiene inercia sincrónica", frequency: "la frecuencia sale del rango",
};

export function lineName(network: Network, id: string): string {
  const line = network.lines.find((l) => l.id === id);
  const node = (nid: string) => network.nodes.find((n) => n.id === nid)?.name.replace(/^S\/E /, "") ?? nid;
  return line ? `${node(line.a)} – ${node(line.b)} (${Math.round(line.kv)} kV)` : id;
}

/** Why: every sentence is built from fixed templates, so the narration is reproducible and carries no model text. */
export function narrate(event: Event, network: Network): string {
  const p = event.params;
  const names = event.ids.map((id) => lineName(network, id)).join(" y ");
  switch (event.text_key) {
    case "line_cut": return `Se corta la línea ${names}.`;
    case "line_overload_open": return `${names} supera el 120% de su capacidad y se abre.`;
    case "island_formed": return `Se forma una isla de ${p.buses} barras con ${p.gen_mw} MW de generación y ${p.load_mw} MW de demanda.`;
    case "load_shed": return `Desconexión automática de carga en ${ZONES[String(p.zone)] ?? p.zone}, escalón ${p.step}: ${p.mw} MW.`;
    case "island_blackout": return `Apagón en una isla de ${p.buses} barras (${p.load_mw} MW): ${REASONS[String(p.reason)] ?? p.reason}${p.min_hz != null ? ` (mínimo ${p.min_hz} Hz)` : ""}.`;
    case "island_stable": return `La isla se estabiliza (frecuencia mínima ${p.min_hz} Hz).`;
    default: return event.text_key;
  }
}

export function formatPeople(n: number): string {
  return n >= 1e6 ? `${(n / 1e6).toLocaleString("es-CL", { maximumFractionDigits: 1 })} millones` : n.toLocaleString("es-CL");
}
