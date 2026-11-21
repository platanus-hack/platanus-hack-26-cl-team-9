import type { Layer } from "@deck.gl/core";
import { IconLayer } from "@deck.gl/layers";
import coalUrl from "../assets/icons/plant-coal.png?url";
import windUrl from "../assets/icons/plant-wind.png?url";
import solarUrl from "../assets/icons/plant-solar.png?url";
import hydroUrl from "../assets/icons/plant-hydro.png?url";
import gasUrl from "../assets/icons/plant-gas.png?url";
import geothermalUrl from "../assets/icons/plant-geothermal.png?url";
import biomassUrl from "../assets/icons/plant-biomass.png?url";
import storageUrl from "../assets/icons/storage-battery.png?url";
import powerUrl from "../assets/icons/power-bolt.png?url";
import towerUrl from "../assets/icons/grid-tower.png?url";
import breakerUrl from "../assets/icons/grid-breaker.png?url";
import transformerUrl from "../assets/icons/grid-transformer.png?url";

/**
 * Flat icons for the 2D view (plants, storage, substations). Nothing feeds the layer yet: to draw icons, build
 * IconPoint[] and pass it as `icons` in the View. They draw only in 2D so the 3D view stays clean.
 *
 * The image files are in web/src/assets/icons/ (bundled by Vite, so they work offline) (512 x 512 PNG, black outline on transparent). The layer tints them
 * with `mask: true`, so any color works on the dark map.
 */
export type IconKind =
  | "coal" | "wind" | "solar" | "hydro" | "gas" | "geothermal" | "biomass" // generation, by carrier in baseline_opf.json
  | "storage" | "power"                                                       // storage and generic energy
  | "tower" | "breaker" | "transformer";                                      // grid equipment (design.md)

export const ICON_FILES: Record<IconKind, string> = {
  coal: coalUrl, // coal thermal plant
  wind: windUrl, // wind farm
  solar: solarUrl, // solar plant
  hydro: hydroUrl, // hydro (reservoir and run-of-river): water drop with a bolt
  gas: gasUrl, // gas: gas cylinder
  geothermal: geothermalUrl, // geothermal: plant with a bolt and an underground pipe
  biomass: biomassUrl, // biomass (ASSUMPTION): plant with a sprout and wind; also fits any renewable thermal plant
  storage: storageUrl, // battery storage
  power: powerUrl, // generic energy (bolt)
  tower: towerUrl, // high-voltage lattice tower (dark gray, not black)
  breaker: breakerUrl, // breaker (switch)
  transformer: transformerUrl, // transformer
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
