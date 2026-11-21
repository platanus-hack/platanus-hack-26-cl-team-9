import type { Layer } from "@deck.gl/core";
import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import populationUrl from "../../../data/processed/geo/population.json?url";
import type { DependencyNode, Network } from "./types";

/** What a heat map shows. Each one answers a question about people and the grid. */
export type HeatKind = "none" | "population" | "dependency" | "criticality";

export const HEAT_OPTIONS: { kind: HeatKind; label: string; hint: string }[] = [
  { kind: "none", label: "Ninguno", hint: "" },
  { kind: "population", label: "Población", hint: "Dónde viven las personas que atiende la red: más claro, más gente." },
  { kind: "dependency", label: "Dependencia de generadores", hint: "Personas que dependen de cada generador, según por dónde le llega la energía (reparto proporcional del flujo). Más claro, más gente." },
  { kind: "criticality", label: "Criticidad de subestaciones", hint: "Qué se pierde sin respaldo si cae la subestación, de 0 a 1. Más intenso, más crítica." },
];

type Rgba = [number, number, number, number];
const RAMPS: Record<Exclude<HeatKind, "none">, Rgba[]> = {
  population: [[255, 241, 218, 0], [255, 241, 218, 40], [255, 241, 218, 90], [255, 241, 218, 150], [255, 241, 218, 210], [255, 255, 255, 255]],
  dependency: [[63, 177, 234, 0], [63, 177, 234, 40], [63, 177, 234, 100], [122, 190, 240, 160], [190, 225, 250, 215], [255, 255, 255, 255]],
  criticality: [[255, 90, 72, 0], [255, 90, 72, 50], [255, 90, 72, 110], [255, 110, 90, 170], [255, 160, 140, 220], [255, 235, 225, 255]],
};

export type PopulationPoint = [lon: number, lat: number, people: number];
let populationLoad: Promise<PopulationPoint[]> | null = null;
/** Served population per substation (data/processed/geo/population.json), bundled with the app so it works offline. */
export function loadPopulation(): Promise<PopulationPoint[]> {
  populationLoad ??= fetch(populationUrl).then((r) => r.json());
  return populationLoad;
}

export interface HeatData { population: PopulationPoint[] | null; dependency: Record<string, DependencyNode> | null; network: Network }

/** The heat layer for a kind, or none while its data is not there yet (older cache without `dependency.json`). */
export function heatLayers(kind: HeatKind, d: HeatData): Layer[] {
  if (kind === "none") return [];
  const common = { id: `heat-${kind}`, colorRange: RAMPS[kind], threshold: 0.03, intensity: 2, aggregation: "SUM" as const };
  if (kind === "population") {
    if (!d.population) return [];
    return [new HeatmapLayer<PopulationPoint>({ ...common, data: d.population, getPosition: (p) => [p[0], p[1]], getWeight: (p) => p[2], radiusPixels: 50 })];
  }
  if (!d.dependency) return [];
  const rows = d.network.nodes.filter((n) => d.dependency![n.id]).map((n) => ({ lon: n.lon, lat: n.lat, dep: d.dependency![n.id] }));
  const weight = kind === "dependency" ? (r: (typeof rows)[number]) => r.dep.people_fed : (r: (typeof rows)[number]) => r.dep.criticality * 1e6;
  return [new HeatmapLayer<(typeof rows)[number]>({ ...common, data: rows.filter((r) => weight(r) > 0), getPosition: (r) => [r.lon, r.lat], getWeight: weight, radiusPixels: 65 })];
}
