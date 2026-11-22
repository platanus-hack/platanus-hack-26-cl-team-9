import { DEFAULT_COUNTRY } from "../map/country";

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
