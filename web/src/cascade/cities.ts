/**
 * Reference cities from the Paper design (Hackaton/2d.css). Metadata only: nothing draws them, because Mapbox already
 * labels these cities and the map showed them twice. Kept for the future interface (search, camera jumps, breadcrumb).
 */
export const CITIES: { name: string; lon: number; lat: number; side: "left" | "right" }[] = [
  { name: "Arica", lon: -70.3126, lat: -18.4783, side: "left" },
  { name: "Antofagasta", lon: -70.3975, lat: -23.6509, side: "left" },
  { name: "Calama", lon: -68.9294, lat: -22.4544, side: "right" },
  { name: "Santiago", lon: -70.6693, lat: -33.4489, side: "left" },
  { name: "Concepción", lon: -73.0444, lat: -36.8201, side: "left" },
  { name: "Puerto Montt", lon: -72.9424, lat: -41.4693, side: "left" },
];
