import type { Layer } from "@deck.gl/core";
import { TripsLayer } from "@deck.gl/geo-layers";
import { ColumnLayer, PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { ViewMode } from "../map/baseMap";
import { iconLayers, type IconPoint } from "./icons";
import { RECTANGLE_BASE } from "../map/shapes";
import type { BusState, EdgeState, Frame, NetLine, NetNode, Network } from "./types";

type Rgba = [number, number, number, number];

// One source for the colours: the map and the legend read these.
export const LOADING_BANDS: { upTo: number; color: Rgba; label: string }[] = [
  { upTo: 0.6, color: [52, 211, 153, 220], label: "Hasta 60% de su capacidad" },
  { upTo: 0.9, color: [250, 204, 21, 230], label: "60% a 90%" },
  { upTo: 1.0, color: [249, 115, 22, 240], label: "90% a 100%" },
  { upTo: Infinity, color: [239, 68, 68, 255], label: "Sobre 100% (sobrecarga)" },
];
export const OPEN_COLOR: Rgba = [239, 68, 68, 200];
export const NO_FLOW_COLOR: Rgba = [90, 100, 120, 120];
export const SELECTED_COLOR: Rgba = [255, 255, 255, 255];
export const WIDTH_BY_KV: { minKv: number; width: number; label: string }[] = [
  { minKv: 500, width: 4, label: "500 kV" },
  { minKv: 220, width: 2.5, label: "220 a 499 kV" },
  { minKv: 0, width: 1.5, label: "Menos de 220 kV" },
];
export const COLUMN_COLOR: Rgba = [96, 165, 250, 230];
export const MW_TO_METERS = 90;      // column height per MW of demand, exaggerated to read at country scale
export const MIN_FLOW_MW = 60;       // flows below this draw no moving dots

export function loadingColor(state: EdgeState | undefined): Rgba {
  if (!state) return NO_FLOW_COLOR;
  if (state.status === "open") return OPEN_COLOR;
  return LOADING_BANDS.find((b) => state.loading <= b.upTo)!.color;
}

const lineWidth = (l: NetLine) => WIDTH_BY_KV.find((w) => l.kv >= w.minKv)!.width;

export interface View { network: Network; buses: Record<string, BusState>; frame: Frame; time: number; selected: string | null; mode: ViewMode; icons?: IconPoint[] }

/** Flat network with the load as 3D columns; dots move along each line in the direction of the flow. */
export function buildCascadeLayers(v: View): Layer[] {
  const node = new Map<string, NetNode>(v.network.nodes.map((n) => [n.id, n]));
  const dark = new Set(v.frame.dark);
  const pos = (id: string): [number, number] => [node.get(id)!.lon, node.get(id)!.lat];
  return [
    new PathLayer<NetLine>({
      id: "lines", data: v.network.lines, pickable: true, widthUnits: "pixels", capRounded: true,
      getPath: (l) => [pos(l.a), pos(l.b)], getColor: (l) => l.id === v.selected ? SELECTED_COLOR : loadingColor(v.frame.edges[l.id]),
      getWidth: (l) => (v.frame.edges[l.id]?.status === "open" ? 1.5 : lineWidth(l)),
      updateTriggers: { getColor: [v.frame, v.selected], getWidth: [v.frame] },
    }),
    new TripsLayer<{ path: [number, number][]; timestamps: number[]; color: Rgba }>({
      id: "flow", data: flowTrips(v, pos), getPath: (d) => d.path, getTimestamps: (d) => d.timestamps, getColor: (d) => d.color,
      currentTime: v.time, trailLength: 0.25, widthMinPixels: 4, capRounded: true, fadeTrail: true,
    }),
    v.mode === "2d" ? _demandSquares(v, dark) : new ColumnLayer<NetNode>({
      id: "load", data: v.network.nodes.filter((n) => (v.buses[n.id]?.load_mw ?? 0) > 20), pickable: true, extruded: true,
      vertices: RECTANGLE_BASE, diskResolution: 4, radiusUnits: "pixels", radius: 4, getPosition: (n) => [n.lon, n.lat],
      getElevation: (n) => (dark.has(n.id) ? 0 : v.buses[n.id].load_mw) * MW_TO_METERS,
      getFillColor: (n) => (dark.has(n.id) ? [0, 0, 0, 0] : COLUMN_COLOR),
      updateTriggers: { getElevation: [v.frame], getFillColor: [v.frame] },
    }),
    new ScatterplotLayer<NetNode>({
      id: "nodes", data: v.network.nodes, pickable: true, radiusUnits: "pixels", getPosition: (n) => [n.lon, n.lat],
      getRadius: (n) => (dark.has(n.id) ? 5 : n.kv >= 500 ? 5 : 3), getFillColor: (n) => (dark.has(n.id) ? [239, 68, 68, 255] : [226, 232, 240, 255]),
      stroked: dark.size > 0, getLineColor: [0, 0, 0, 255], lineWidthMinPixels: 1, updateTriggers: { getFillColor: [v.frame], getRadius: [v.frame] },
    }),
    ...(v.mode === "2d" ? iconLayers(v.icons ?? []) : []),
  ];
}

/** Seen from above there is no height, so demand is a flat disc whose area grows with MW (radius ~ sqrt of MW). */
function _demandSquares(v: View, dark: Set<string>) {
  return new ScatterplotLayer<NetNode>({
    id: "load-2d", data: v.network.nodes.filter((n) => (v.buses[n.id]?.load_mw ?? 0) > 20 && !dark.has(n.id)), pickable: true,
    radiusUnits: "pixels", getPosition: (n) => [n.lon, n.lat], getRadius: (n) => Math.sqrt(v.buses[n.id].load_mw) * 0.5,
    getFillColor: [COLUMN_COLOR[0], COLUMN_COLOR[1], COLUMN_COLOR[2], 150], updateTriggers: { getRadius: [v.frame], getFillColor: [v.frame] },
  });
}

const DOT_COUNT = 3;

function flowTrips(v: View, pos: (id: string) => [number, number]) {
  const trips: { path: [number, number][]; timestamps: number[]; color: Rgba }[] = [];
  for (const line of v.network.lines) {
    const edge = v.frame.edges[line.id];
    if (!edge || edge.status === "open" || Math.abs(edge.flow_mw) < MIN_FLOW_MW) continue;
    const path = edge.flow_mw > 0 ? [pos(line.a), pos(line.b)] : [pos(line.b), pos(line.a)];
    for (let k = 0; k < DOT_COUNT; k++) trips.push({ path, timestamps: [k / DOT_COUNT, k / DOT_COUNT + 1], color: [255, 255, 255, 255] });
  }
  return trips;
}
