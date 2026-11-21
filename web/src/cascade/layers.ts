import type { Layer } from "@deck.gl/core";
import { TripsLayer } from "@deck.gl/geo-layers";
import { ColumnLayer, PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import type { BusState, EdgeState, Frame, NetLine, NetNode, Network } from "./types";

type Rgba = [number, number, number, number];

export function loadingColor(state: EdgeState | undefined): Rgba {
  if (!state) return [90, 100, 120, 120];
  if (state.status === "open") return [239, 68, 68, 200];
  const r = state.loading;
  if (r > 1.0) return [239, 68, 68, 255];
  if (r > 0.9) return [249, 115, 22, 240];
  if (r > 0.6) return [250, 204, 21, 230];
  return [52, 211, 153, 220];
}

const lineWidth = (l: NetLine) => (l.kv >= 500 ? 4 : l.kv >= 220 ? 2.5 : 1.5);

export interface View { network: Network; buses: Record<string, BusState>; frame: Frame; time: number; selected: string | null }

/** Flat network with the load as 3D columns; dots move along each line in the direction of the flow. */
export function buildCascadeLayers(v: View): Layer[] {
  const node = new Map<string, NetNode>(v.network.nodes.map((n) => [n.id, n]));
  const dark = new Set(v.frame.dark);
  const pos = (id: string): [number, number] => [node.get(id)!.lon, node.get(id)!.lat];
  return [
    new PathLayer<NetLine>({
      id: "lines", data: v.network.lines, pickable: true, widthUnits: "pixels", capRounded: true,
      getPath: (l) => [pos(l.a), pos(l.b)], getColor: (l) => l.id === v.selected ? [255, 255, 255, 255] : loadingColor(v.frame.edges[l.id]),
      getWidth: (l) => (v.frame.edges[l.id]?.status === "open" ? 1.5 : lineWidth(l)),
      updateTriggers: { getColor: [v.frame, v.selected], getWidth: [v.frame] },
    }),
    new TripsLayer<{ path: [number, number][]; timestamps: number[]; color: Rgba }>({
      id: "flow", data: flowTrips(v, pos), getPath: (d) => d.path, getTimestamps: (d) => d.timestamps, getColor: (d) => d.color,
      currentTime: v.time, trailLength: 0.25, widthMinPixels: 4, capRounded: true, fadeTrail: true,
    }),
    new ColumnLayer<NetNode>({
      id: "load", data: v.network.nodes.filter((n) => (v.buses[n.id]?.load_mw ?? 0) > 20), pickable: true, extruded: true,
      diskResolution: 10, radiusUnits: "pixels", radius: 4, getPosition: (n) => [n.lon, n.lat],
      getElevation: (n) => (dark.has(n.id) ? 0 : v.buses[n.id].load_mw) * 90,
      getFillColor: (n) => (dark.has(n.id) ? [0, 0, 0, 0] : [96, 165, 250, 230]),
      updateTriggers: { getElevation: [v.frame], getFillColor: [v.frame] },
    }),
    new ScatterplotLayer<NetNode>({
      id: "nodes", data: v.network.nodes, pickable: true, radiusUnits: "pixels", getPosition: (n) => [n.lon, n.lat],
      getRadius: (n) => (dark.has(n.id) ? 5 : n.kv >= 500 ? 5 : 3), getFillColor: (n) => (dark.has(n.id) ? [239, 68, 68, 255] : [226, 232, 240, 255]),
      stroked: dark.size > 0, getLineColor: [0, 0, 0, 255], lineWidthMinPixels: 1, updateTriggers: { getFillColor: [v.frame], getRadius: [v.frame] },
    }),
  ];
}

const DOT_COUNT = 3;
const MIN_FLOW_MW = 60;

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
