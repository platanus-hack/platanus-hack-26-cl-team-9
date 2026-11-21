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
  /** Size in pixels on screen. Default 18. */
  size?: number;
  /** Text for the tooltip. */
  label?: string;
}

export function iconLayers(points: IconPoint[]): Layer[] {
  if (!points.length) return [];
  return [new IconLayer<IconPoint>({
    id: "icons-2d", data: points, pickable: true, getPosition: (p) => [p.lon, p.lat], getIcon: (p) => p.icon, getSize: (p) => p.size ?? 18, sizeUnits: "pixels",
  })];
}
