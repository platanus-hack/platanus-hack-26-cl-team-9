import type { Layer } from "@deck.gl/core";
import { IconLayer } from "@deck.gl/layers";

/**
 * Flat icons for the 2D view (plants, storage, substations). Nothing feeds the layer yet: to draw icons, build
 * IconPoint[] and pass it as `icons` in the View. They draw only in 2D so the 3D view stays clean.
 *
 * The image files are in web/public/icons/ (512 x 512 PNG, black outline on transparent). The layer tints them
 * with `mask: true`, so any color works on the dark map.
 */
export type IconKind = "coal" | "wind" | "solar" | "storage" | "power";

export const ICON_FILES: Record<IconKind, string> = {
  coal: "/icons/plant-coal.png",          // coal thermal plant
  wind: "/icons/plant-wind.png",          // wind farm
  solar: "/icons/plant-solar.png",        // solar plant
  storage: "/icons/storage-battery.png",  // battery storage
  power: "/icons/power-bolt.png",         // generic energy (bolt)
};

export interface IconPoint {
  id: string;
  lon: number;
  lat: number;
  kind: IconKind;
  /** Size in meters on the ground, so the icon grows when you zoom in (clamped to 12 to 40 pixels on screen). Default 8000. */
  size?: number;
  /** RGBA tint. Default cream, the "cities" color of design.md. */
  color?: [number, number, number, number];
  /** Text for the tooltip. */
  label?: string;
}

const DEFAULT_COLOR: [number, number, number, number] = [255, 241, 218, 255];

export function iconLayers(points: IconPoint[]): Layer[] {
  if (!points.length) return [];
  return [new IconLayer<IconPoint>({
    id: "icons-2d", data: points, pickable: true, getPosition: (p) => [p.lon, p.lat],
    getIcon: (p) => ({ url: ICON_FILES[p.kind], width: 512, height: 512, mask: true }),
    getColor: (p) => p.color ?? DEFAULT_COLOR, getSize: (p) => p.size ?? 8000, sizeUnits: "meters", sizeMinPixels: 12, sizeMaxPixels: 40,
  })];
}
