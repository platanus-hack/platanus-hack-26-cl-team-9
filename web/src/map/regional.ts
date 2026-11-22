import type { Layer } from "@deck.gl/core";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { hex, NODE_COLOR, tierOf, type ColorMode } from "../cascade/layers";
import chileUrl from "../../../data/processed/chile.geojson?url";
import { outlineOf } from "./countryBounds";
import { TECH_COLORS, TECH_NAMES, type Rgb } from "./layers";

type OutlineFile = Parameters<typeof outlineOf>[0];

export type LonLat = [number, number];

// Files built by `cascadasen-regional` and data/scripts/build_latam_outlines.sh (docs/regional.md).
// A glob, not fixed imports, so the app still builds when the layer has not been generated.
const FILES = import.meta.glob("../../../data/processed/latam/**/*.{geojson,json}", { query: "?url", import: "default", eager: true }) as Record<string, string>;
const urlOf = (suffix: string): string | undefined => Object.entries(FILES).find(([path]) => path.endsWith(suffix))?.[1];

export const regionalOutlineUrl = urlOf("/latam/outlines.geojson");

export interface RegionalSource { id: string; name: string; publisher: string; url: string; license: string; attribution: string }
export interface RegionalCountry {
  country: string; name: string; counts: { lines: number; substations: number; plants: number }; raw_counts: { lines: number; substations: number; plants: number };
  plant_count: number; sources: RegionalSource[]; warnings: string[];
  /** km of reduced line per kV ("500": 2889) and installed MW per technology, as `cascadasen-regional` writes them. */
  line_km_by_kv?: Record<string, number>; plant_mw_by_tech?: Record<string, number>;
}
export interface RegionalLine { id: string; country: string; kv: number; circuits: number | null; lengthKm: number | null; source: string; path: LonLat[] }
export interface RegionalSubstation { id: string; country: string; name: string; kv: number; kind: string; source: string; position: LonLat }
export interface RegionalPlant { id: string; country: string; name: string; tech: string | null; mw: number; count: number; source: string; position: LonLat }
export interface RegionalGrid { countries: RegionalCountry[]; lines: RegionalLine[]; substations: RegionalSubstation[]; plants: RegionalPlant[] }

interface Feature<G, P> { geometry: G; properties: P }
interface Collection<G, P> { features: Feature<G, P>[] }
type Props = { id: string; country?: string; name: string; source: string; kv: number; kind: string; circuits: number | null; length_km: number | null; tech: string | null; mw: number; count: number };

/** ISO3 of the countries whose drawn layer is in the build (docs/regional.md section 1). */
export const regionalCountries: string[] = [...new Set(Object.keys(FILES).map((path) => path.match(/\/latam\/([A-Z]{3})\/substations\.geojson$/)?.[1]).filter((iso): iso is string => !!iso))].sort();

let manifest: Promise<{ countries: Record<string, RegionalCountry> }> | null = null;
const grids = new Map<string, Promise<RegionalGrid>>();

/** Why: only one network is drawn at a time (issue #49), so only the chosen country is fetched, once. No physics runs on it. */
export function loadCountryGrid(iso: string): Promise<RegionalGrid> {
  let grid = grids.get(iso);
  if (!grid) {
    grid = _loadCountry(iso);
    grids.set(iso, grid);
    grid.catch(() => grids.delete(iso)); // a failed fetch can be retried
  }
  return grid;
}

async function _loadCountry(iso: string): Promise<RegionalGrid> {
  const manifestUrl = urlOf("/latam/manifest.json");
  if (manifestUrl && !manifest) manifest = _fetchJson(manifestUrl);
  const [entry, lines, substations, plants] = await Promise.all([
    manifest ? manifest.then((m) => m.countries[iso]).catch(() => undefined) : Promise.resolve(undefined),
    ...["lines", "substations", "plants"].map((layer) => {
      const url = urlOf(`/latam/${iso}/${layer}.geojson`);
      return url ? _fetchJson<Collection<{ coordinates: unknown }, Props>>(url) : Promise.resolve({ features: [] });
    }),
  ]) as [RegionalCountry | undefined, ...Collection<{ coordinates: unknown }, Props>[]];
  const country = (p: Props) => p.country || iso;
  return {
    countries: entry ? [entry] : [],
    lines: lines.features.map((f) => ({ id: f.properties.id, country: country(f.properties), kv: f.properties.kv, circuits: f.properties.circuits, lengthKm: f.properties.length_km, source: f.properties.source, path: f.geometry.coordinates as LonLat[] })),
    substations: substations.features.map((f) => ({ id: f.properties.id, country: country(f.properties), name: f.properties.name, kv: f.properties.kv, kind: f.properties.kind, source: f.properties.source, position: f.geometry.coordinates as LonLat })),
    plants: plants.features.map((f) => ({ id: f.properties.id, country: country(f.properties), name: f.properties.name, tech: f.properties.tech, mw: f.properties.mw, count: f.properties.count, source: f.properties.source, position: f.geometry.coordinates as LonLat })),
  };
}

/** The same grid from the context documents the backend composed (docs/grids.md): already in this shape, only joined. */
/** Documents built before the `country` field was added per element take the document's country (`countryOf` rule). */
type DocElement<T> = Omit<T, "country"> & { country?: string };
export function regionalFromDocuments(docs: { meta: RegionalCountry; lines: DocElement<RegionalLine>[]; substations: DocElement<RegionalSubstation>[]; plants: DocElement<RegionalPlant>[] }[]): RegionalGrid {
  const tag = <T,>(d: { meta: RegionalCountry }, x: DocElement<T>) => ({ ...x, country: x.country || d.meta.country }) as T;
  return {
    countries: docs.map((d) => d.meta),
    lines: docs.flatMap((d) => d.lines.map((x) => tag<RegionalLine>(d, x))),
    substations: docs.flatMap((d) => d.substations.map((x) => tag<RegionalSubstation>(d, x))),
    plants: docs.flatMap((d) => d.plants.map((x) => tag<RegionalPlant>(d, x))),
  };
}

const withAlpha = (c: Rgb, a: number): [number, number, number, number] => [c[0], c[1], c[2], a];
const OTHER_TECH: Rgb = [200, 200, 200];
/** Not part of the load ramp (green to red), so it reads as "no data" in the Simulación view. */
export const REGIONAL_NO_LOAD = "#767B80";

/**
 * Lines and substations drawn exactly like Chile's (cascade/layers.ts): same voltage tiers, widths and node style.
 * In the load view they are neutral gray: they carry no load, and the green of the ramp would claim "< 50 %".
 * Not clickable as a cut: the layer ids start with "regional-" and the tooltip says they are not simulated.
 */
export function buildRegionalLayers(grid: RegionalGrid, colorMode: ColorMode = "voltage"): Layer[] {
  const lineColor = colorMode === "voltage" ? (l: RegionalLine) => hex(tierOf(l.kv).color) : () => hex(REGIONAL_NO_LOAD);
  return [
    new PathLayer<RegionalLine>({
      id: "regional-lines", data: grid.lines, pickable: true, widthUnits: "pixels", capRounded: true, getPath: (l) => l.path,
      getColor: lineColor, getWidth: (l) => tierOf(l.kv).width, updateTriggers: { getColor: colorMode },
    }),
    new ScatterplotLayer<RegionalSubstation>({
      id: "regional-substations", data: grid.substations, pickable: true, radiusUnits: "pixels", getPosition: (s) => s.position,
      getRadius: (s) => (s.kv >= 500 ? 3 : 2), getFillColor: hex(NODE_COLOR, 200),
    }),
    // Plants are solid discs in their technology colour with a dark rim (docs/design.md section 3), smaller than before so
    // they never hide the lines; none of the colours is red, which means failure (E-28, G-06).
    new ScatterplotLayer<RegionalPlant>({
      id: "regional-plants", data: grid.plants, pickable: true, radiusUnits: "pixels", getPosition: (p) => p.position,
      getRadius: (p) => Math.min(8, 2 + Math.sqrt(p.mw) * 0.16), getFillColor: (p) => withAlpha(TECH_COLORS[p.tech ?? ""] ?? OTHER_TECH, 235),
      stroked: true, lineWidthUnits: "pixels", getLineWidth: 1, getLineColor: [24, 25, 27, 255],
    }),
  ];
}

const FOOT = "Red solo para ver: no se simula";
const num = (n: number) => n.toLocaleString("es-CL", { maximumFractionDigits: 1 });
/** "EPE WebMap capa 17; EPE WebMap capa 18" -> "Fuente: EPE WebMap": the publisher, not its layer numbers (D11). */
const sourceLine = (s: string) => `Fuente: ${[...new Set(s.split(";").map((x) => x.replace(/\s*capa \d+\s*$/i, "").trim()).filter(Boolean))].join(", ")}`;

export function regionalTooltip(layerId: string, object: unknown): string | null {
  if (layerId === "regional-lines") {
    const l = object as RegionalLine;
    return `Línea de ${num(l.kv)} kV${l.circuits && l.circuits > 1 ? ` · ${l.circuits} circuitos` : ""}${l.lengthKm ? ` · ${num(Math.round(l.lengthKm))} km` : ""}\n${sourceLine(l.source)}\n${FOOT}`;
  }
  if (layerId === "regional-substations") {
    const s = object as RegionalSubstation;
    return `${s.name || (s.kind === "junction" ? "Derivación de línea" : "Subestación")}\n${num(s.kv)} kV\n${sourceLine(s.source)}\n${FOOT}`;
  }
  if (layerId === "regional-plants") {
    const p = object as RegionalPlant;
    const tech = p.tech ? (TECH_NAMES[p.tech] ?? p.tech).toLowerCase() : "otra tecnología";
    return `${p.name || "Generación"}\n${p.count} ${p.count === 1 ? "central" : "centrales"} · ${tech} · ${num(Math.round(p.mw))} MW\n${sourceLine(p.source)}\n${FOOT}`;
  }
  return null;
}

async function _fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`No se pudo cargar ${url}: ${response.status}`);
  return response.json() as Promise<T>;
}

const outlines = new Map<string, Promise<OutlineFile | null>>();

/** A country's outline (chile.geojson for Chile, its features of latam/outlines.geojson otherwise), or null when there is none. */
export function loadOutline(iso: string): Promise<OutlineFile | null> {
  let out = outlines.get(iso);
  if (!out) {
    const url = iso === "CHL" ? chileUrl : regionalOutlineUrl;
    out = url ? _fetchJson<OutlineFile>(url).then((file) => outlineOf(file, iso)).then((o) => (o.features.length ? o : null)).catch(() => null) : Promise.resolve(null);
    outlines.set(iso, out);
  }
  return out;
}
