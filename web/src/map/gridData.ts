import { fetchJson } from "../lib/fetchJson";
import chileUrl from "../../../data/processed/chile.geojson?url";
import linesUrl from "../../../data/processed/geo/lines.geojson?url";
import plantsUrl from "../../../data/processed/geo/plants.geojson?url";
import substationsUrl from "../../../data/processed/geo/substations.geojson?url";

export type LonLat = [number, number];

export interface Line { name: string; kv: number | null; path: LonLat[] }
export interface Substation { id: string; name: string; kv: number | null; position: LonLat }
export interface Plant { node: string; tech: string; mw: number | null }
export interface GenerationNode { id: string; name: string; position: LonLat; mw: number; tech: string }

export interface GridData {
  outlineUrl: string;
  lines: Line[];
  substations: Substation[];
  generation: GenerationNode[];
}

interface Feature<G, P> { geometry: G; properties: P }
interface Collection<G, P> { features: Feature<G, P>[] }

/** Why: the map reads the processed grid files from the repo (data/processed/geo), no physics here. */
export async function loadGridDataWorkflow(): Promise<GridData> {
  const [lines, substations, plants] = await Promise.all([
    fetchJson<Collection<{ coordinates: LonLat[] }, { name: string; kv: number | null }>>(linesUrl),
    fetchJson<Collection<{ coordinates: LonLat }, { id: string; name: string; kv: number | null; in_main_grid: boolean }>>(substationsUrl),
    fetchJson<Collection<unknown, Plant>>(plantsUrl),
  ]);
  const mainGrid = _mainGridSubstations(substations);
  return {
    outlineUrl: chileUrl,
    lines: _toLines(lines),
    substations: mainGrid,
    generation: aggregatePlantsByNode(plants.features.map((f) => f.properties), _allSubstations(substations)),
  };
}

/**
 * One column per substation with summed MW and its dominant technology (docs/stack.md 5.2):
 * 1,245 loose plant columns look like noise.
 */
export function aggregatePlantsByNode(plants: Plant[], substations: Substation[]): GenerationNode[] {
  const byId = new Map(substations.map((s) => [s.id, s]));
  const totals = new Map<string, Map<string, number>>();
  for (const plant of plants) {
    if (!plant.mw || !byId.has(plant.node)) continue;
    const techs = totals.get(plant.node) ?? new Map<string, number>();
    techs.set(plant.tech, (techs.get(plant.tech) ?? 0) + plant.mw);
    totals.set(plant.node, techs);
  }
  return [...totals].map(([node, techs]) => {
    const [tech] = [...techs].reduce((best, entry) => (entry[1] > best[1] ? entry : best));
    const { name, position } = byId.get(node)!;
    return { id: node, name, position, tech, mw: [...techs.values()].reduce((a, b) => a + b, 0) };
  });
}

function _toLines(collection: Collection<{ coordinates: LonLat[] }, { name: string; kv: number | null }>): Line[] {
  return collection.features.map((f) => ({ name: f.properties.name, kv: f.properties.kv, path: f.geometry.coordinates }));
}

function _allSubstations(collection: Collection<{ coordinates: LonLat }, { id: string; name: string; kv: number | null }>): Substation[] {
  return collection.features.map((f) => ({ id: f.properties.id, name: f.properties.name, kv: f.properties.kv, position: f.geometry.coordinates }));
}

function _mainGridSubstations(collection: Collection<{ coordinates: LonLat }, { id: string; name: string; kv: number | null; in_main_grid: boolean }>): Substation[] {
  const inMain = new Set(collection.features.filter((f) => f.properties.in_main_grid).map((f) => f.properties.id));
  return _allSubstations(collection).filter((s) => inMain.has(s.id));
}
