import { changeText } from "../assistant/labels";
import type { Edits, StressChange } from "../cascade/edits";
import { changesOf } from "../cascade/edits";
import type { Prepared } from "../cascade/gridsApi";
import { cutName, narrate, placeName } from "../cascade/text";
import type { Network, Timeline } from "../cascade/types";
import type { CyberArea, CyberFrame } from "../cyber/cyber";

/**
 * Historial de cambios: what happened to the network. `ajuste` is a change someone made (the user, or the assistant);
 * `caida` is something that failed (a disaster's first failures, the cascade that follows, a cyberattack).
 * `ids` are the lines (R###) or substations (B###) the entry touches: a click on it shows them on the map, and a
 * cascade's own "line cut" is not listed twice for a user's cut. `change` keys a factor change, so the substations the
 * server resolved for it (POST /grids/prepare) can be attached when they arrive.
 */
export type EntryKind = "ajuste" | "caida";
export interface Entry { kind: EntryKind; text: string; when: string; ids: string[]; change?: string }

/** A change's scope without its amount: the same scope with a new factor is one "changed" entry, not removed + added. */
const scopeOf = (c: StressChange) => JSON.stringify({ ...c, factor: undefined, add: undefined, x_factor: undefined });
const nameOf = (network: Network) => (id: string) =>
  /^B\d+$/.test(id) ? cutName(network, `sub-${id}`) : /^R\d+$/.test(id) ? cutName(network, id) : id;

/** Adjustments between two sets of changes: cuts and substations switched off or back on, and factors set or changed. */
export function diffEdits(prev: Edits, next: Edits, network: Network): Entry[] {
  const out: Entry[] = [];
  const name = nameOf(network);
  const add = (text: string, ids: string[], change?: string) => out.push({ kind: "ajuste", text, ids, when: "", change });
  for (const id of next.lines.filter((x) => !prev.lines.includes(x))) add(`Línea cortada: ${name(id)}.`, [id]);
  for (const id of prev.lines.filter((x) => !next.lines.includes(x))) add(`Línea repuesta: ${name(id)}.`, [id]);
  for (const id of next.buses.filter((x) => !prev.buses.includes(x))) add(`Subestación apagada: ${name(id)}.`, [id]);
  for (const id of prev.buses.filter((x) => !next.buses.includes(x))) add(`Subestación encendida: ${name(id)}.`, [id]);
  const before = new Map(changesOf(prev).map((c) => [scopeOf(c), c]));
  const after = new Map(changesOf(next).map((c) => [scopeOf(c), c]));
  const ownIds = (c: StressChange) => [...(c.buses ?? []), ...(c.lines ?? [])];
  for (const [scope, c] of after) {
    const old = before.get(scope);
    if (old && JSON.stringify(old) === JSON.stringify(c)) continue;
    const text = changeText(c as unknown as Record<string, unknown>, name);
    add(old ? `Cambio: ${text} (antes ${amountOf(old)}).` : `${capital(text)}${scopeHint(c)}.`, ownIds(c), JSON.stringify(c));
  }
  for (const [scope, c] of before) if (!after.has(scope)) add(`Se quita: ${changeText(c as unknown as Record<string, unknown>, name)}.`, ownIds(c));
  return out;
}

const amountOf = (c: StressChange) =>
  c.add !== undefined ? `${c.add >= 0 ? "+" : ""}${c.add.toLocaleString("es-CL")}${c.target === "population" ? "" : " MW"}` : `× ${(c.factor ?? c.x_factor ?? 1).toLocaleString("es-CL")}`;
const capital = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
/** A change without a place filter applies to the whole network: say so. */
const scopeHint = (c: StressChange) => ([c.places, c.comunas, c.buses, c.areas, c.zones, c.lines].some((x) => x?.length) ? "" : " en toda la red");

/**
 * The substations the server resolved for the current changes, attached to their entries. One substation: its name
 * goes in the text; more: how many, and the click shows them.
 */
export function withPrepared(entries: Entry[], current: StressChange[], prepared: Prepared | null, network: Network): Entry[] {
  if (!prepared) return entries;
  const byKey = new Map(current.map((c, i) => [JSON.stringify(c), prepared.changes[i]]));
  const name = nameOf(network);
  return entries.map((e) => {
    const p = e.change ? byKey.get(e.change) : undefined;
    const ids = (p?.elements ?? []).map((x) => x.id).filter((id) => /^[BR]\d+$/.test(id));
    if (!p || !ids.length) return e;
    const where = ids.length === 1 ? name(ids[0]) : `${ids.length} subestaciones`;
    return { ...e, ids, text: `${e.text.replace(/\.$/, "")} · ${where}.` };
  });
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
