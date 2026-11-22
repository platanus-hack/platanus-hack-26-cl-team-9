import { ColumnLayer, GeoJsonLayer, PathLayer } from "@deck.gl/layers";
import type { GenerationNode, GridData, Line, Substation } from "./gridData";
import { RECTANGLE_BASE, SQUARE_BASE } from "./shapes";

export type Rgb = [number, number, number];

// Colours match the teammate's atlas legend (data/processed/atlas_sen.html).
export const KV_COLORS: [number, Rgb][] = [
  [500, [255, 200, 60]],
  [345, [255, 110, 199]],
  [220, [255, 120, 60]],
  [154, [180, 130, 255]],
  [110, [60, 200, 190]],
  [66, [90, 130, 230]],
];
export const LOW_KV_COLOR: Rgb = [110, 120, 140];

// Red is reserved for failures (docs/design.md section 3): thermal is a grayish brown, never red or purple.
export const TECH_COLORS: Record<string, Rgb> = {
  solar: [255, 196, 0],
  eolica: [140, 230, 255],
  hidro: [40, 120, 255],
  termica: [156, 128, 104],
  bioenergia: [90, 200, 90],
  geotermica: [220, 90, 220],
  nuclear: [170, 160, 235],
};
/** Spanish names of the technologies, for legends and tooltips. */
export const TECH_NAMES: Record<string, string> = {
  solar: "Solar", eolica: "Eólica", hidro: "Hidroeléctrica", termica: "Térmica", bioenergia: "Bioenergía", geotermica: "Geotérmica", nuclear: "Nuclear",
};
const OTHER_TECH_COLOR: Rgb = [200, 200, 200];

// Map-scale exaggeration: a 1,500 MW node is ~180 km tall so it reads at country zoom.
const METERS_PER_MW = 120;
const METERS_PER_KV = 30;

/** Flat 2D base (outline, lines) with the grid elements standing in 3D on top. */
// The outline is only needed on the offline base map; Mapbox already draws land and borders.
export function buildGridLayers(grid: GridData, { withOutline = true } = {}) {
  const gridLayers = [_linesLayer(grid.lines), _substationsLayer(grid.substations), _generationLayer(grid.generation)];
  return withOutline ? [_outlineLayer(grid.outlineUrl), ...gridLayers] : gridLayers;
}

export function kvColor(kv: number | null): Rgb {
  return KV_COLORS.find(([min]) => (kv ?? 0) >= min)?.[1] ?? LOW_KV_COLOR;
}

function _outlineLayer(url: string) {
  return new GeoJsonLayer({
    id: "chile-outline",
    data: url,
    stroked: true,
    filled: true,
    getFillColor: [16, 24, 40],
    getLineColor: [60, 80, 115],
    lineWidthMinPixels: 1,
  });
}

function _linesLayer(lines: Line[]) {
  return new PathLayer<Line>({
    id: "lines",
    data: lines,
    pickable: true,
    getPath: (d) => d.path,
    getColor: (d) => kvColor(d.kv),
    getWidth: (d) => ((d.kv ?? 0) >= 500 ? 3 : (d.kv ?? 0) >= 220 ? 1.8 : 1),
    widthUnits: "pixels",
    capRounded: true,
    jointRounded: true,
    opacity: 0.85,
  });
}

function _substationsLayer(substations: Substation[]) {
  return new ColumnLayer<Substation>({
    id: "substations",
    data: substations,
    pickable: true,
    extruded: true,
    vertices: SQUARE_BASE, diskResolution: 4,
    radiusUnits: "pixels",
    radius: 2.5,
    getPosition: (d) => d.position,
    getElevation: (d) => Math.max(d.kv ?? 0, 20) * METERS_PER_KV,
    getFillColor: (d) => kvColor(d.kv),
  });
}

function _generationLayer(nodes: GenerationNode[]) {
  return new ColumnLayer<GenerationNode>({
    id: "generation",
    data: nodes,
    pickable: true,
    extruded: true,
    vertices: RECTANGLE_BASE, diskResolution: 4,
    radiusUnits: "pixels",
    radius: 4,
    getPosition: (d) => d.position,
    getElevation: (d) => d.mw * METERS_PER_MW,
    getFillColor: (d) => TECH_COLORS[d.tech] ?? OTHER_TECH_COLOR,
  });
}
