import { TECH_COLORS } from "../map/layers";
import type { StressChange } from "./edits";
import type { Prepared } from "./gridsApi";
import type { Network } from "./types";

/** A point the prepared scenario added (a datacenter, a plant, a battery), drawn as a pin on the map. A plant's pin takes
 * its technology color, as on the map and in the legend; a load has none (a ring). */
export interface PlacedPoint { key: string; lon: number; lat: number; label: string; name: string; kind: "load" | "gen"; color: string | null }
const THERMAL = new Set(["carbon", "gas", "diesel", "termica_otra", "termica"]);
const OTHER_COLOR = "rgb(200, 200, 200)";

const TECH: Record<string, string> = {
  solar: "solar", eolica: "eólica", hidro: "hidro", carbon: "carbón", gas: "gas", diesel: "diésel", bioenergia: "bioenergía",
  geotermica: "geotérmica", termica: "térmica", termica_otra: "térmica", bateria: "batería",
};
const MAX_PINS_PER_CHANGE = 5; // an `add` spread over a whole zone is not a point

/**
 * The points a prepared scenario added: each change that adds demand or generation (`add` > 0) at a few substations, at
 * the substations the server reports in `prepared` (where a place resolved to). Without the pin the map showed nothing,
 * because with changes and no failure it draws the base case (docs/stress.md section 10).
 */
export function placedPoints(changes: StressChange[], prepared: Prepared | null, network: Network | null): PlacedPoint[] {
  if (!prepared || !network) return [];
  const nodes = new Map(network.nodes.map((n) => [n.id, n]));
  const out: PlacedPoint[] = [];
  changes.forEach((c, i) => {
    if ((c.target !== "demand" && c.target !== "generation") || !c.add || c.add <= 0) return;
    const elements = prepared.changes[i]?.elements ?? [];
    if (!elements.length || elements.length > MAX_PINS_PER_CHANGE) return;
    const tech = prepared.changes[i]?.tech ?? c.tech;
    const what = c.target === "demand" ? "de demanda" : techLabel(tech);
    const color = c.target === "demand" ? null : techColor(tech);
    for (const e of elements) {
      const pair = c.target === "demand" ? e.load_mw : e.gen_mw;
      const node = nodes.get(e.id);
      const delta = pair ? pair[1] - pair[0] : 0;
      if (!node || delta <= 0) continue;
      const label = `+${Math.round(delta).toLocaleString("es-CL")} MW ${what}`;
      out.push({ key: `${i}-${e.id}`, lon: node.lon, lat: node.lat, label, name: node.name, kind: c.target === "demand" ? "load" : "gen", color });
    }
  });
  return out;
}

function techColor(tech: string[] | undefined): string {
  const kinds = [...new Set((tech ?? []).map((t) => (THERMAL.has(t) ? "termica" : t)))];
  const rgb = kinds.length === 1 ? TECH_COLORS[kinds[0]] : undefined;
  return rgb ? `rgb(${rgb.join(", ")})` : OTHER_COLOR;
}

function techLabel(tech: string[] | undefined): string {
  const names = [...new Set((tech ?? []).map((t) => TECH[t] ?? t))];
  return names.length === 1 ? names[0] : "de generación";
}
