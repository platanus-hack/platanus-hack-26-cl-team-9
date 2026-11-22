import type { Layer } from "@deck.gl/core";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import type { BusState, DependencyNode, Network } from "./types";

/** What a heat map shows. Each one answers a question about people and the grid as it stands.
 *  "affected" (people without supply at this second) is toggled from the Simulación tab, so it is not in HEAT_OPTIONS. */
export type HeatKind = "none" | "population" | "dependency" | "criticality" | "affected";

export const HEAT_OPTIONS: { kind: HeatKind; label: string; hint: string }[] = [
  { kind: "none", label: "Ninguno", hint: "" },
  { kind: "population", label: "Población", hint: "Personas que atiende cada subestación en este punto de operación: más claro, más gente." },
  { kind: "dependency", label: "Dependencia de generadores", hint: "Personas que dependen de cada generador, según por dónde le llega la energía (reparto proporcional del flujo), con los cambios de Estado de la red aplicados. Más claro, más gente." },
  { kind: "criticality", label: "Criticidad de subestaciones", hint: "Qué se pierde sin respaldo si cae la subestación, de 0 a 1, en la red tal como quedó tras los cambios. Más intenso, más crítica." },
];

/** The maps that need the server (POST /api/v1/grids/dependency); population reads the buses already loaded. */
export const needsDependency = (kind: HeatKind) => kind === "dependency" || kind === "criticality";

type Rgba = [number, number, number, number];
const RAMPS: Record<Exclude<HeatKind, "none">, Rgba[]> = {
  population: [[255, 241, 218, 0], [255, 241, 218, 40], [255, 241, 218, 90], [255, 241, 218, 150], [255, 241, 218, 210], [255, 255, 255, 255]],
  dependency: [[63, 177, 234, 0], [63, 177, 234, 40], [63, 177, 234, 100], [122, 190, 240, 160], [190, 225, 250, 215], [255, 255, 255, 255]],
  criticality: [[255, 90, 72, 0], [255, 90, 72, 50], [255, 90, 72, 110], [255, 110, 90, 170], [255, 160, 140, 220], [255, 235, 225, 255]],
  affected: [[255, 90, 72, 0], [255, 90, 72, 50], [255, 90, 72, 110], [255, 110, 90, 170], [255, 160, 140, 220], [255, 235, 225, 255]],
};

export interface HeatPoint { lon: number; lat: number; weight: number }

/** Weighted points of a heat map: one per substation with something to show. `dark`: buses without supply at this second. */
export function heatPoints(kind: HeatKind, network: Network, buses: Record<string, BusState>, dependency: Record<string, DependencyNode> | null, dark: ReadonlySet<string> = new Set()): HeatPoint[] {
  if (kind === "none" || (needsDependency(kind) && !dependency)) return [];
  const weight = (id: string) => kind === "population" ? buses[id]?.people ?? 0
    : kind === "affected" ? (dark.has(id) ? buses[id]?.people ?? 0 : 0)
    : kind === "dependency" ? dependency![id]?.people_fed ?? 0
    : (dependency![id]?.criticality ?? 0) * 1e6;
  return network.nodes.map((n) => ({ lon: n.lon, lat: n.lat, weight: weight(n.id) })).filter((p) => p.weight > 0);
}

export function heatLayers(kind: HeatKind, points: HeatPoint[]): Layer[] {
  if (kind === "none" || !points.length) return [];
  return [new HeatmapLayer<HeatPoint>({
    id: `heat-${kind}`, data: points, colorRange: RAMPS[kind], threshold: 0.03, intensity: 2, aggregation: "SUM",
    getPosition: (p) => [p.lon, p.lat], getWeight: (p) => p.weight, radiusPixels: kind === "population" || kind === "affected" ? 50 : 65,
  })];
}
