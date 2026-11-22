import { DEFAULT_COUNTRY } from "../map/country";
import { changesOf, type Edits } from "./edits";
import { SUBSTATION_PREFIX } from "./text";

/** The operating point a bare `/` opens. */
export const DEFAULT_POINT = "feb2025-0300"; // Demanda mínima: where the app always starts

export interface UrlState {
  pointId: string;
  cut: string | null;
  sid: string | null;
  /** ISO3 of the network shown; uploaded networks live only in this browser and pass the default. */
  country?: string;
}

/**
 * The search string that mirrors the current view, carrying only values that differ from the defaults.
 * Keeps every other param (sesion, mapa, limite). A session pins its own point and owns its cut, so both are dropped.
 * `pais` names a network other than Chile's; a session is always Chile's.
 * Returns "" when nothing is left, so the default view is a bare `/`.
 */
export function syncedSearch(search: string, { pointId, cut, sid, country = DEFAULT_COUNTRY }: UrlState): string {
  const q = new URLSearchParams(search);
  if (!sid && country !== DEFAULT_COUNTRY) q.set("pais", country);
  else q.delete("pais");
  if (!sid && pointId !== DEFAULT_POINT) q.set("point", pointId);
  else q.delete("point");
  if (!sid && cut) q.set("cut", cut);
  else q.delete("cut");
  q.delete("vista"); // the 3D view was removed: an old ?vista=3d link opens the 2D map
  const s = q.toString();
  return s ? `?${s}` : "";
}

/**
 * The `cut` param that describes the changes, or null when they cannot be written in the URL. A link carries one change:
 * a line (`R239`) or a substation shutdown (`sub-B012`); several changes or a prepared scenario are not written, so a
 * reload of such a link starts clean and offers to restore them (`startEdits` in edits.ts).
 */
export function urlCutOf(e: Edits): string | null {
  if (changesOf(e).length) return null;
  if (e.lines.length === 1 && e.buses.length === 0) return e.lines[0];
  if (e.buses.length === 1 && e.lines.length === 0) return `${SUBSTATION_PREFIX}${e.buses[0]}`;
  return null;
}

/** The point a link asks for when it exists; otherwise the default one, with the unknown id so the app can say so. */
export function resolvePoint(requested: string | null, known: string[]): { pointId: string; unknown: string | null } {
  if (!requested || known.includes(requested)) return { pointId: requested ?? DEFAULT_POINT, unknown: null };
  return { pointId: DEFAULT_POINT, unknown: requested };
}
