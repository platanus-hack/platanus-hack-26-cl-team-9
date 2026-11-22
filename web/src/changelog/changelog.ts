import type { Edits } from "../cascade/edits";
import { changesOf } from "../cascade/edits";
import { cutName, narrate, placeName } from "../cascade/text";
import type { Network, Timeline } from "../cascade/types";
import type { CyberArea, CyberFrame } from "../cyber/cyber";

/**
 * Historial de cambios: what happened to the network. `ajuste` is a change someone made (the user, or the assistant);
 * `caida` is something that failed (a disaster's first failures, the cascade that follows, a cyberattack).
 * `ids` are the lines or substations the entry names, so a cascade's own "line cut" is not listed twice for a user's cut.
 */
export type EntryKind = "ajuste" | "caida";
export interface Entry { kind: EntryKind; text: string; when: string; ids: string[] }

const targetName = (network: Network, id: string) => cutName(network, id);

/** Adjustments between two sets of changes: cuts and substations switched off or back on, and factors set. */
export function diffEdits(prev: Edits, next: Edits, network: Network): Entry[] {
  const out: Entry[] = [];
  const add = (text: string, ids: string[]) => out.push({ kind: "ajuste", text, ids, when: "" });
  for (const id of next.lines.filter((x) => !prev.lines.includes(x))) add(`Línea cortada: ${targetName(network, id)}.`, [id]);
  for (const id of prev.lines.filter((x) => !next.lines.includes(x))) add(`Línea repuesta: ${targetName(network, id)}.`, [id]);
  for (const id of next.buses.filter((x) => !prev.buses.includes(x))) add(`Subestación apagada: ${targetName(network, `sub-${id}`)}.`, [id]);
  for (const id of prev.buses.filter((x) => !next.buses.includes(x))) add(`Subestación encendida: ${targetName(network, `sub-${id}`)}.`, [id]);
  const before = changesOf(prev).map((c) => JSON.stringify(c));
  const after = changesOf(next).map((c) => JSON.stringify(c));
  for (const c of changesOf(next)) if (!before.includes(JSON.stringify(c))) add(`Ajuste ×${c.factor ?? "?"} en ${describeTarget(c, network)}.`, []);
  for (const c of changesOf(prev)) if (!after.includes(JSON.stringify(c))) add(`Ajuste quitado en ${describeTarget(c, network)}.`, []);
  return out;
}

function describeTarget(c: { target: string; lines?: string[]; buses?: string[] }, network: Network): string {
  const ids = (c.target === "lines" ? c.lines : c.buses) ?? [];
  if (!ids.length) return c.target === "lines" ? "líneas" : "subestaciones";
  const name = (id: string) => (c.target === "lines" ? cutName(network, id) : cutName(network, `sub-${id}`));
  return ids.slice(0, 3).map(name).join(", ") + (ids.length > 3 ? ` y ${ids.length - 3} más` : "");
}

const FALLS = new Set(["line_cut", "line_overload_open", "island_blackout", "load_shed"]);

/**
 * Falls of a simulated cascade, in time order. A `line_cut` of a line the user cut by hand is dropped (it is already an
 * adjustment); a disaster's own first cut stays: those are its initial failures.
 */
export function cascadeEntries(tl: Timeline, network: Network, userIds: ReadonlySet<string>): Entry[] {
  return tl.events
    .filter((e) => FALLS.has(e.type) || FALLS.has(e.text_key))
    .filter((e) => !(e.text_key === "line_cut" && e.ids.length > 0 && e.ids.every((id) => userIds.has(id))))
    .map((e) => ({ kind: "caida" as const, text: narrate(e, network), ids: e.ids, when: `t+${Math.round(e.t)} s` }));
}

/** Cyberattack events of a run: an area compromised or struck is a fall; one eradicated is a repair (adjustment). */
export function cyberEntries(frames: CyberFrame[], areas: CyberArea[]): Entry[] {
  const name = (id: string) => placeName(areas.find((a) => a.id === id)?.name ?? id);
  const out: Entry[] = [];
  for (const f of frames) {
    for (const e of f.events) {
      const when = `ciclo ${f.cycle}`;
      if (e.kind === "compromised") out.push({ kind: "caida", text: `Ciberataque: intrusión en ${name(e.area)}.`, when, ids: [] });
      else if (e.kind === "struck") out.push({ kind: "caida", text: `Ciberataque: ${name(e.area)} golpeada, pierde suministro.`, when, ids: [] });
      else if (e.kind === "eradicated") out.push({ kind: "ajuste", text: `Defensa: ${name(e.area)} limpiada y repuesta.`, when, ids: [] });
    }
  }
  return out;
}
