import type { Layer } from "@deck.gl/core";
import { IconLayer } from "@deck.gl/layers";

/**
 * Contract for the 2D-only icon layer (plants, towers, transformers... from design.md). Nothing feeds it yet:
 * to add icons, build IconPoint[] and pass it as `icons` in the View. They draw only in 2D so the 3D view stays clean.
 */
export interface IconPoint {
  id: string;
  lon: number;
  lat: number;
  /** Image of the icon: an url or data url, with its pixel size. */
  icon: { url: string; width: number; height: number };
  /** Size in meters on the ground, so the icon grows when you zoom in (clamped to 12 to 40 pixels on screen). Default 8000. */
  size?: number;
  /** Text for the tooltip. */
  label?: string;
}

export function iconLayers(points: IconPoint[]): Layer[] {
  if (!points.length) return [];
  return [new IconLayer<IconPoint>({
    id: "icons-2d", data: points, pickable: true, getPosition: (p) => [p.lon, p.lat], getIcon: (p) => p.icon, getSize: (p) => p.size ?? 8000, sizeUnits: "meters", sizeMinPixels: 12, sizeMaxPixels: 40,
  })];
}
