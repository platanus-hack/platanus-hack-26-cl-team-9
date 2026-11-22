import { placeName } from "./text";
import type { BusState, ComunaPeople, Network } from "./types";

/** One comuna (or one substation without comuna data) and the people it has without supply at this second.
 *  `total`: people the model assigns to that comuna. `is_assumption`: the comuna is only partly dark, so its count
 *  depends on the comuna-to-substation split (shown as "estimado"). */
export interface AffectedRow { key: string; name: string; people: number; total: number; is_assumption: boolean }
export interface Affected { people: number; rows: AffectedRow[] }

/** People without supply grouped by comuna: the people of the dark buses, split as comunas-<year>.json says.
 *  Each bus's rows are scaled to its current `people`, so prepared scenarios and sessions match the heat map. */
export function affectedByComuna(dark: ReadonlySet<string>, buses: Record<string, BusState>, network: Network, file: ComunaPeople | null): Affected {
  const rows = new Map<string, AffectedRow>();
  const lit = new Set<string>(); // comunas served by at least one bus that still has supply
  let people = 0;
  for (const node of network.nodes) {
    const busPeople = buses[node.id]?.people ?? 0;
    const isDark = dark.has(node.id);
    if (isDark) people += busPeople;
    const split = file?.buses[node.id] ?? [];
    const sum = split.reduce((s, [, n]) => s + n, 0);
    if (!split.length || sum <= 0) {
      if (isDark && busPeople > 0) rows.set(`bus:${node.id}`, { key: `bus:${node.id}`, name: placeName(node.name) || node.id, people: busPeople, total: busPeople, is_assumption: true });
      continue;
    }
    for (const [cut, n] of split) {
      const share = (n / sum) * busPeople;
      const row = rows.get(cut) ?? { key: cut, name: file!.comunas[cut] ?? cut, people: 0, total: 0, is_assumption: false };
      row.total += share;
      if (isDark) row.people += share;
      else if (share > 0) lit.add(cut);
      rows.set(cut, row);
    }
  }
  const list = [...rows.values()]
    .map((r) => (lit.has(r.key) ? { ...r, is_assumption: true } : r))
    .filter((r) => r.people >= 0.5)
    .sort((a, b) => b.people - a.people || a.name.localeCompare(b.name, "es"));
  return { people, rows: list };
}
