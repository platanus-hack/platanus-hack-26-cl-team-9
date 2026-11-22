import type { Pick } from "./clicks";
import { lineName, placeName } from "./text";
import type { Network } from "./types";

/** One entry of the cold start search: what it selects, the text the field shows and a short kind for the list. */
export interface SearchOption { pick: Pick; value: string; kind: string }

/**
 * Every line and substation of the network by its readable name: the keyboard route to select one (D8). Two elements
 * with the same name get a number ("(2)"), so each text selects exactly one. Substations first, then lines, each by name.
 */
export function searchOptions(network: Network): SearchOption[] {
  const nodes = network.nodes.map((n) => ({ pick: { kind: "node", id: n.id } as Pick, value: placeName(n.name), kind: `Subestación · ${Math.round(n.kv)} kV` }));
  const lines = network.lines.map((l) => ({ pick: { kind: "line", id: l.id } as Pick, value: lineName(network, l.id), kind: `Línea · ${Math.round(l.kv)} kV` }));
  const byName = (a: SearchOption, b: SearchOption) => a.value.localeCompare(b.value, "es");
  const out = [...nodes.sort(byName), ...lines.sort(byName)];
  const seen = new Map<string, number>();
  return out.map((o) => {
    const n = (seen.get(o.value) ?? 0) + 1;
    seen.set(o.value, n);
    return n > 1 ? { ...o, value: `${o.value} (${n})` } : o;
  });
}

const fold = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();

/** The name without the owner and voltage tags in parentheses: "Polpaico (TRANSELEC)" is found as "Polpaico". */
const bare = (s: string) => fold(s.replace(/\s*\([^)]*\)/g, ""));

/**
 * The option the text names (accents and case ignored): the exact name first, then the one whose name without its
 * parenthetical tags is the text, then the only option that contains it. Null when none or several match.
 */
export function findOption(options: SearchOption[], text: string): SearchOption | null {
  const q = fold(text);
  if (!q) return null;
  const exact = options.find((o) => fold(o.value) === q);
  if (exact) return exact;
  const tagless = options.filter((o) => bare(o.value) === bare(text));
  if (tagless.length === 1) return tagless[0];
  const partial = matches(options, text);
  return partial.length === 1 ? partial[0] : null;
}

/** Options whose name contains the text, for the "several match" message. */
export const matches = (options: SearchOption[], text: string) => { const q = fold(text); return q ? options.filter((o) => fold(o.value).includes(q)) : []; };
