import type { ViewMode } from "../map/baseMap";

/** The operating point a bare `/` opens. */
export const DEFAULT_POINT = "nov2026-1300";

export interface UrlState {
  pointId: string;
  cut: string | null;
  mode: ViewMode;
  sid: string | null;
}

/**
 * The search string that mirrors the current view, carrying only values that differ from the defaults.
 * Keeps every other param (sesion, mapa, limite). A session pins its own point and owns its cut, so both are dropped.
 * Returns "" when nothing is left, so the default view is a bare `/`.
 */
export function syncedSearch(search: string, { pointId, cut, mode, sid }: UrlState): string {
  const q = new URLSearchParams(search);
  if (!sid && pointId !== DEFAULT_POINT) q.set("point", pointId);
  else q.delete("point");
  if (!sid && cut) q.set("cut", cut);
  else q.delete("cut");
  if (mode === "3d") q.set("vista", "3d");
  else q.delete("vista");
  const s = q.toString();
  return s ? `?${s}` : "";
}
