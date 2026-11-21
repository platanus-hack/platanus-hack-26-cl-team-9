import type { Layer } from "@deck.gl/core";
import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { buildCascadeLayers } from "../cascade/layers";
import type { BusState, Frame } from "../cascade/types";
import type { ViewMode } from "../map/baseMap";
import type { Crew, Posture, TheaterArea, TheaterNetwork, TheaterSnapshot } from "./types";

type Rgba = [number, number, number, number];

// One source for the colours of the operation mode: the map and the legend read these.
export const POSTURE_COLOR: Record<Posture, Rgba> = {
  normal: [148, 163, 184, 255],
  manual: [251, 191, 36, 255],
  segmented: [167, 139, 250, 255],
};
export const POSTURE_LABEL: Record<Posture, string> = {
  normal: "Operación normal",
  manual: "Operación local (manual)",
  segmented: "Red digital aislada (segmentada)",
};
export const CREW_COLOR: Rgba = [34, 211, 238, 255];
export const CREW_BUSY_COLOR: Rgba = [244, 114, 182, 255];
export const AREA_RADIUS_M = 55_000;

/** Short map labels for the effects in force in an area (effect level only, never a technique). */
export const EFFECT_SHORT: Record<string, string> = {
  C1_generation_loss: "pérdida de generación",
  C2_common_mode_loss: "pérdida por zona",
  C3_transmission_opening: "transmisión abierta",
  C4_defense_not_acting: "defensa sin actuar",
  C5_remote_dispatch_loss: "sin despacho remoto",
  D1_telemetry_loss: "sin telemetría",
  D2_telemetry_delay: "datos atrasados",
  D3_unreliable_data: "datos dudosos",
  D4_comms_loss: "sin comunicaciones",
  D5_false_alarms: "falsas alarmas",
  D6_external_dependency_loss: "servicio externo caído",
  E1_demand_surge: "alza de demanda",
  E2_renewable_drop: "baja renovable",
};

export interface OperationView {
  network: TheaterNetwork;
  snapshot: TheaterSnapshot;
  frame: Frame; // snapshot.grid, or a frame of snapshot.transient while replaying the cascade
  time: number;
  selected: string | null;
  mode: ViewMode;
  dispatched: Record<string, number>; // crew id -> cycle it was sent (from the executed actions seen so far)
}

/** Area fill: posture colour, more opaque the less supervision sees (observability 1 = clear). */
export function areaFill(posture: Posture, observability: number): Rgba {
  const [r, g, b] = POSTURE_COLOR[posture];
  const alpha = Math.round(25 + 120 * Math.min(1, Math.max(0, 1 - observability)) + (posture === "normal" ? 0 : 40));
  return [r, g, b, Math.min(200, alpha)];
}

/** Where a crew is drawn: on its way from its position to the target substation, linearly by cycle. */
export function crewPosition(crew: Crew, net: TheaterNetwork, cycle: number, dispatchedAt: number | undefined): [number, number] {
  const from: [number, number] = [crew.lon, crew.lat];
  if (crew.status !== "busy" || !crew.target_bus || crew.arrival == null) return from;
  const node = net.nodes.find((n) => n.id === crew.target_bus);
  if (!node) return from;
  const start = dispatchedAt ?? crew.arrival - 1;
  const span = Math.max(1, crew.arrival - start);
  const f = Math.min(1, Math.max(0, (cycle - start) / span));
  return [from[0] + (node.lon - from[0]) * f, from[1] + (node.lat - from[1]) * f];
}

/** Served load per bus for the mapa 3 columns (dark buses come from the frame). */
export function servedBuses(net: TheaterNetwork, frame: Frame & { buses?: Record<string, number> }): Record<string, BusState> {
  const out: Record<string, BusState> = {};
  for (const [id, b] of Object.entries(net.buses)) out[id] = { ...b, load_mw: frame.buses?.[id] ?? b.load_mw };
  return out;
}

export function buildOperationLayers(v: OperationView): Layer[] {
  const base = buildCascadeLayers({ network: v.network, buses: servedBuses(v.network, v.frame), frame: v.frame, time: v.time, selected: v.selected, mode: v.mode });
  const areas = v.network.areas;
  const state = (a: TheaterArea) => v.snapshot.areas[a.id] ?? { observability: 1, posture: "normal" as Posture, effects: [] };
  const labelled = areas.filter((a) => state(a).effects.length > 0 || state(a).posture !== "normal");
  return [
    new ScatterplotLayer<TheaterArea>({
      id: "areas", data: areas, pickable: true, radiusUnits: "meters", getRadius: AREA_RADIUS_M, stroked: true, lineWidthMinPixels: 1,
      getPosition: (a) => [a.lon, a.lat], getFillColor: (a) => areaFill(state(a).posture, state(a).observability),
      getLineColor: (a) => POSTURE_COLOR[state(a).posture], updateTriggers: { getFillColor: [v.snapshot], getLineColor: [v.snapshot] },
    }),
    ...base,
    new TextLayer<TheaterArea>({
      id: "area-effects", data: labelled, getPosition: (a) => [a.lon + 0.9, a.lat], getText: (a) => _areaText(a, state(a)),
      getSize: 11, getColor: [241, 245, 249, 230], getTextAnchor: "start", getAlignmentBaseline: "center", fontFamily: "system-ui, sans-serif",
      background: true, getBackgroundColor: [15, 23, 42, 190], backgroundPadding: [4, 2], updateTriggers: { getText: [v.snapshot] },
    }),
    new ScatterplotLayer<Crew>({
      id: "crews", data: v.snapshot.crews, pickable: true, radiusUnits: "pixels", getRadius: 6, stroked: true,
      getLineColor: [15, 23, 42, 255], lineWidthMinPixels: 2,
      getPosition: (c) => crewPosition(c, v.network, v.snapshot.cycle, v.dispatched[c.id]),
      getFillColor: (c) => (c.status === "busy" ? CREW_BUSY_COLOR : CREW_COLOR), updateTriggers: { getPosition: [v.snapshot], getFillColor: [v.snapshot] },
    }),
  ];
}

function _areaText(a: TheaterArea, s: { posture: Posture; effects: { type: string }[] }): string {
  const parts = [...new Set(s.effects.map((e) => EFFECT_SHORT[e.type] ?? e.type))];
  if (s.posture !== "normal") parts.unshift(s.posture === "manual" ? "operación local" : "aislada");
  return `${a.id} · ${parts.join(" · ")}`;
}
