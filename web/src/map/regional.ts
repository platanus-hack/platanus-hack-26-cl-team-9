import type { Layer } from "@deck.gl/core";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { kvColor, TECH_COLORS, type Rgb } from "./layers";

export type LonLat = [number, number];

// Files built by `cascadasen-regional` and data/scripts/build_latam_outlines.sh (docs/regional.md).
// A glob, not fixed imports, so the app still builds when the layer has not been generated.
const FILES = import.meta.glob("../../../data/processed/latam/**/*.{geojson,json}", { query: "?url", import: "default", eager: true }) as Record<string, string>;
const urlOf = (suffix: string): string | undefined => Object.entries(FILES).find(([path]) => path.endsWith(suffix))?.[1];

export const regionalOutlineUrl = urlOf("/latam/outlines.geojson");

export interface RegionalSource { id: string; name: string; publisher: string; url: string; license: string; attribution: string }
export interface RegionalCountry { country: string; name: string; counts: { lines: number; substations: number; plants: number }; sources: RegionalSource[]; warnings: string[] }
export interface RegionalLine { id: string; name: string; kv: number; lengthKm: number | null; source: string; path: LonLat[] }
export interface RegionalSubstation { id: string; name: string; kv: number; source: string; position: LonLat }
export interface RegionalPlant { id: string; name: string; tech: string | null; mw: number; source: string; position: LonLat }
export interface RegionalGrid { countries: RegionalCountry[]; lines: RegionalLine[]; substations: RegionalSubstation[]; plants: RegionalPlant[] }

interface Feature<G, P> { geometry: G; properties: P }
interface Collection<G, P> { features: Feature<G, P>[] }
type Props = { id: string; name: string; source: string; kv: number; length_km: number | null; tech: string | null; mw: number };

/** Why: the other countries' grids are context drawn under Chile's; no physics runs on them. */
export async function loadRegionalGrid(): Promise<RegionalGrid | null> {
  const manifestUrl = urlOf("/latam/manifest.json");
  if (!manifestUrl) return null;
  const manifest = await _fetchJson<{ countries: Record<string, RegionalCountry> }>(manifestUrl);
  const grid: RegionalGrid = { countries: Object.values(manifest.countries), lines: [], substations: [], plants: [] };
  await Promise.all(Object.keys(manifest.countries).map(async (iso) => {
    const [lines, substations, plants] = await Promise.all(["lines", "substations", "plants"].map((layer) => {
      const url = urlOf(`/latam/${iso}/${layer}.geojson`);
      return url ? _fetchJson<Collection<{ coordinates: unknown }, Props>>(url) : Promise.resolve({ features: [] });
    }));
    grid.lines.push(...lines.features.map((f) => ({ id: f.properties.id, name: f.properties.name, kv: f.properties.kv, lengthKm: f.properties.length_km, source: f.properties.source, path: f.geometry.coordinates as LonLat[] })));
    grid.substations.push(...substations.features.map((f) => ({ id: f.properties.id, name: f.properties.name, kv: f.properties.kv, source: f.properties.source, position: f.geometry.coordinates as LonLat })));
    grid.plants.push(...plants.features.map((f) => ({ id: f.properties.id, name: f.properties.name, tech: f.properties.tech, mw: f.properties.mw, source: f.properties.source, position: f.geometry.coordinates as LonLat })));
  }));
  return grid;
}

const DIM = 130; // alpha: context, quieter than Chile's grid
const withAlpha = (c: Rgb, a: number): [number, number, number, number] => [c[0], c[1], c[2], a];
const OTHER_TECH: Rgb = [200, 200, 200];

/** Flat context layers under Chile's grid. Not clickable as a cut: the tooltip says they are not simulated. */
export function buildRegionalLayers(grid: RegionalGrid): Layer[] {
  return [
    new PathLayer<RegionalLine>({
      id: "regional-lines", data: grid.lines, pickable: true, widthUnits: "pixels", getPath: (l) => l.path,
      getColor: (l) => withAlpha(kvColor(l.kv), DIM), getWidth: (l) => (l.kv >= 500 ? 2.5 : l.kv >= 220 ? 1.8 : 1.2), capRounded: true,
    }),
    new ScatterplotLayer<RegionalSubstation>({
      id: "regional-substations", data: grid.substations, pickable: true, radiusUnits: "pixels", getPosition: (s) => s.position,
      getRadius: (s) => (s.kv >= 500 ? 3.5 : 2.2), getFillColor: [226, 232, 240, 150],
    }),
    new ScatterplotLayer<RegionalPlant>({
      id: "regional-plants", data: grid.plants, pickable: true, radiusUnits: "pixels", getPosition: (p) => p.position,
      getRadius: (p) => Math.min(14, 2 + Math.sqrt(p.mw) * 0.28), getFillColor: (p) => withAlpha(TECH_COLORS[p.tech ?? ""] ?? OTHER_TECH, 120),
    }),
  ];
}

const FOOT = "Red de contexto: no se simula";

export function regionalTooltip(layerId: string, object: unknown): string | null {
  if (layerId === "regional-lines") {
    const l = object as RegionalLine;
    return `${l.name || "Línea"}\n${l.kv} kV${l.lengthKm ? ` · ${Math.round(l.lengthKm)} km` : ""}\n${l.source}\n${FOOT}`;
  }
  if (layerId === "regional-substations") {
    const s = object as RegionalSubstation;
    return `${s.name || "Subestación"}\n${s.kv} kV\n${s.source}\n${FOOT}`;
  }
  if (layerId === "regional-plants") {
    const p = object as RegionalPlant;
    return `${p.name || "Central"}\n${p.tech ?? "otra"} · ${Math.round(p.mw)} MW\n${p.source}\n${FOOT}`;
  }
  return null;
}

async function _fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`No se pudo cargar ${url}: ${response.status}`);
  return response.json() as Promise<T>;
}
