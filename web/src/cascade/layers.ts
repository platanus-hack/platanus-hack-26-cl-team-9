import type { Layer } from "@deck.gl/core";
import { TripsLayer } from "@deck.gl/geo-layers";
import { ColumnLayer, PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { ViewMode } from "../map/baseMap";
import { RECTANGLE_BASE } from "../map/shapes";
import type { BusState, EdgeState, Frame, NetLine, NetNode, Network } from "./types";

type Rgba = [number, number, number, number];
const hex = (h: string, a = 255): Rgba => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16), a];

/** What line color means. Design v5: one meaning per color at a time; stroke width always shows voltage. */
export type ColorMode = "voltage" | "load";

// One source for the colours: the map, the legend and the panel read these (Paper Design v5 tokens).
export const FAULT = "#FF5A48";
export const VOLTAGE_TIERS: { label: string; minKv: number; color: string; width: number }[] = [
  { label: "500 kV", minKv: 500, color: "#F0F2F4", width: 3 },
  { label: "154–345 kV", minKv: 154, color: "#F99549", width: 1.8 },
  { label: "100–110 kV", minKv: 100, color: "#3FB1EA", width: 1.3 },
  { label: "44–69 kV", minKv: 44, color: "#7AA5BF", width: 1.1 },
  { label: "Media tensión", minKv: 0, color: "#767B80", width: 1 },
];
export const LOAD_BANDS: { upTo: number; color: string; label: string }[] = [
  { upTo: 0.5, color: "#8E9298", label: "< 50 %" },
  { upTo: 0.75, color: "#C9CBCF", label: "50–75 %" },
  { upTo: 1.0, color: "#E8B4A6", label: "75–100 %" },
  { upTo: Infinity, color: FAULT, label: "> 100 %" },
];
export const DEAD_LINE = "#0E0F10";      // "sin tensión": both ends dark
export const OPEN_LINE = "#8A8B90";      // "fuera": cut or tripped, dashed
export const NODE_COLOR = "#D0D1D4";
export const DEMAND_COLOR = "#FFF1DA";   // cream is reserved for cities and population
export const MW_TO_METERS = 90;          // column height per MW of demand, exaggerated to read at country scale
export const MIN_FLOW_MW = 60;           // flows below this draw no moving dots
const DASH_PX = 5;

export const tierOf = (kv: number) => VOLTAGE_TIERS.find((w) => kv >= w.minKv)!;

export function loadColor(state: EdgeState | undefined): string {
  if (!state) return LOAD_BANDS[0].color;
  return LOAD_BANDS.find((b) => state.loading <= b.upTo)!.color;
}

export interface Toggles { flow: boolean; demand: boolean }
export interface View {
  network: Network; buses: Record<string, BusState>; frame: Frame; time: number; colorMode: ColorMode;
  selectedNode: string | null; mode: ViewMode; zoom: number; toggles: Toggles;
}

/** Flat network on the basemap; optional moving dots for the flow and demand as columns (3D) or discs (2D). */
export function buildCascadeLayers(v: View): Layer[] {
  const node = new Map<string, NetNode>(v.network.nodes.map((n) => [n.id, n]));
  const dark = new Set(v.frame.dark);
  const pos = (id: string): [number, number] => [node.get(id)!.lon, node.get(id)!.lat];
  const status = (l: NetLine) => {
    const e = v.frame.edges[l.id];
    if (e?.status === "open") return "open";
    if (dark.has(l.a) && dark.has(l.b)) return "dead";
    return "live";
  };
  // Stable arrays per frame and zoom step, so deck.gl does not rebuild attributes on every animation tick.
  const parts = partitionCache.get(v.frame) ?? partitionCache.set(v.frame, {
    live: v.network.lines.filter((l) => status(l) === "live"), dead: v.network.lines.filter((l) => status(l) === "dead"),
    open: v.network.lines.filter((l) => status(l) === "open"), dashes: new Map(),
  }).get(v.frame)!;
  const { live, dead, open } = parts;
  const zoomStep = Math.round(v.zoom * 4) / 4;
  const openDashes = parts.dashes.get(zoomStep) ?? parts.dashes.set(zoomStep, dashes(open, pos, zoomStep)).get(zoomStep)!;
  const width = (l: NetLine) => {
    const base = tierOf(l.kv).width;
    return v.colorMode === "load" && (v.frame.edges[l.id]?.loading ?? 0) > 1 ? base + 1.5 : base;
  };
  const color = (l: NetLine) => hex(v.colorMode === "voltage" ? tierOf(l.kv).color : loadColor(v.frame.edges[l.id]));
  const trigger = [v.frame, v.colorMode];
  return [
    new PathLayer<NetLine>({
      id: "lines-dead-outline", data: dead, widthUnits: "pixels", getPath: (l) => [pos(l.a), pos(l.b)],
      getColor: [255, 255, 255, 64], getWidth: (l) => tierOf(l.kv).width + 2, updateTriggers: { getWidth: trigger },
    }),
    new PathLayer<NetLine>({
      id: "lines-dead", data: dead, pickable: true, widthUnits: "pixels", getPath: (l) => [pos(l.a), pos(l.b)],
      getColor: hex(DEAD_LINE), getWidth: (l) => tierOf(l.kv).width, updateTriggers: { getWidth: trigger },
    }),
    new PathLayer<{ line: NetLine; path: [number, number][] }>({
      id: "lines-open", data: openDashes, pickable: true, widthUnits: "pixels", getPath: (d) => d.path,
      getColor: hex(OPEN_LINE), getWidth: 2, 
    }),
    new PathLayer<NetLine>({
      id: "lines", data: live, pickable: true, autoHighlight: true, highlightColor: [255, 255, 255, 255], widthUnits: "pixels", capRounded: true,
      getPath: (l) => [pos(l.a), pos(l.b)], getColor: color, getWidth: width, updateTriggers: { getColor: trigger, getWidth: trigger },
    }),
    ...(v.toggles.flow ? [new TripsLayer<{ path: [number, number][]; timestamps: number[] }>({
      id: "flow", data: flowTrips(v, pos), getPath: (d) => d.path, getTimestamps: (d) => d.timestamps, getColor: [255, 255, 255, 230],
      currentTime: v.time, trailLength: 0.25, widthMinPixels: 3, capRounded: true, fadeTrail: true,
    })] : []),
    ...(v.toggles.demand ? [_demand(v, dark)] : []),
    new ScatterplotLayer<NetNode>({
      id: "nodes", data: v.network.nodes, pickable: true, radiusUnits: "pixels", getPosition: (n) => [n.lon, n.lat],
      getRadius: (n) => (n.id === v.selectedNode ? 6 : n.kv >= 500 ? 3 : 2),
      getFillColor: (n) => (dark.has(n.id) ? hex(DEAD_LINE) : hex(NODE_COLOR, n.id === v.selectedNode ? 255 : 200)),
      stroked: true, lineWidthUnits: "pixels", getLineWidth: (n) => (n.id === v.selectedNode ? 2 : dark.has(n.id) ? 1 : 0),
      getLineColor: (n) => (n.id === v.selectedNode ? [255, 255, 255, 255] : [255, 255, 255, 64]),
      updateTriggers: { getFillColor: [v.frame, v.selectedNode], getRadius: [v.selectedNode], getLineWidth: [v.frame, v.selectedNode], getLineColor: [v.selectedNode] },
    }),
  ];
}

function _demand(v: View, dark: Set<string>): Layer {
  const data = v.network.nodes.filter((n) => (v.buses[n.id]?.load_mw ?? 0) > 20 && !dark.has(n.id));
  const [r, g, b] = hex(DEMAND_COLOR);
  if (v.mode === "2d") {
    // Seen from above there is no height, so demand is a flat disc whose area grows with MW (radius ~ sqrt of MW).
    return new ScatterplotLayer<NetNode>({
      id: "load-2d", data, pickable: true, radiusUnits: "pixels", getPosition: (n) => [n.lon, n.lat],
      getRadius: (n) => Math.sqrt(v.buses[n.id].load_mw) * 0.5, getFillColor: [r, g, b, 70], updateTriggers: { getRadius: [v.frame] },
    });
  }
  return new ColumnLayer<NetNode>({
    id: "load", data, pickable: true, extruded: true, vertices: RECTANGLE_BASE, diskResolution: 4, radiusUnits: "pixels", radius: 4,
    getPosition: (n) => [n.lon, n.lat], getElevation: (n) => v.buses[n.id].load_mw * MW_TO_METERS, getFillColor: [r, g, b, 200],
    updateTriggers: { getElevation: [v.frame] },
  });
}

/** Dashed "fuera" lines: deck.gl has no dash without the extensions package, so each line is cut into short pieces. */
function dashes(lines: NetLine[], pos: (id: string) => [number, number], zoom: number) {
  const degPerPx = 360 / (512 * 2 ** zoom);
  const dash = DASH_PX * degPerPx;
  const out: { line: NetLine; path: [number, number][] }[] = [];
  for (const line of lines) {
    const [a, b] = [pos(line.a), pos(line.b)];
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    const n = Math.max(1, Math.floor(len / dash));
    for (let i = 0; i < n; i += 2) {
      const p = (k: number): [number, number] => [a[0] + ((b[0] - a[0]) * k) / n, a[1] + ((b[1] - a[1]) * k) / n];
      out.push({ line, path: [p(i), p(Math.min(i + 1, n))] });
    }
  }
  return out;
}

const DOT_COUNT = 3;
type Partition = { live: NetLine[]; dead: NetLine[]; open: NetLine[]; dashes: Map<number, { line: NetLine; path: [number, number][] }[]> };
const partitionCache = new WeakMap<Frame, Partition>();

function flowTrips(v: View, pos: (id: string) => [number, number]) {
  const trips: { path: [number, number][]; timestamps: number[] }[] = [];
  for (const line of v.network.lines) {
    const edge = v.frame.edges[line.id];
    if (!edge || edge.status === "open" || Math.abs(edge.flow_mw) < MIN_FLOW_MW) continue;
    const path = edge.flow_mw > 0 ? [pos(line.a), pos(line.b)] : [pos(line.b), pos(line.a)];
    for (let k = 0; k < DOT_COUNT; k++) trips.push({ path, timestamps: [k / DOT_COUNT, k / DOT_COUNT + 1] });
  }
  return trips;
}
