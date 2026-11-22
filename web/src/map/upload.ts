import { isIso3 } from "./iso3";
import type { LonLat, RegionalGrid, RegionalLine, RegionalPlant, RegionalSubstation } from "./regional";

// Limits of docs/network-format.md section 6 (Brazil, the largest network here, is 0.73 MB, 853 buses and 1,305 lines).
export const MAX_BYTES = 10 * 1024 * 1024;
export const MAX_BUSES = 5000;
export const MAX_LINES = 10000;
export const MAX_TEXT = 120;
const MAX_ERRORS = 12;
const DEFAULT_SOURCE = "Red subida por el usuario";

export type UploadFormat = "geojson" | "v1";
export interface UploadOk { ok: true; format: UploadFormat; grid: RegionalGrid; name: string | null; fileCountry: string | null; warnings: string[] }
export interface UploadFail { ok: false; errors: string[] }
export type UploadResult = UploadOk | UploadFail;

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** Untrusted text becomes plain, short text: no control characters, at most MAX_TEXT characters. It is never parsed as HTML. */
export function cleanText(value: unknown, max = MAX_TEXT): string {
  if (typeof value !== "string" && typeof value !== "number") return "";
  return String(value).replace(/[\u0000-\u001f\u007f-\u009f]/g, " ").replace(/\s+/g, " ").trim().slice(0, max);
}

const fmt = (n: number) => n.toLocaleString("es-CL");
/** Short label of an element for an error message; the id is cleaned and cut, React renders it as text. */
const label = (kind: string, i: number, id: unknown) => `${kind} ${i + 1}${cleanText(id, 40) ? ` (${cleanText(id, 40)})` : ""}`;

/**
 * Why: an uploaded file is not trusted. It is read with JSON.parse only (never evaluated), every value is range-checked
 * and copied field by field into new objects, and the declared country is written onto every element (issue #49 part C).
 * Accepts one file in either format of docs/network-format.md: a GeoJSON FeatureCollection in the regional schema v2
 * (section 2, L0) or the v1 network JSON (section 1, like data/processed/latam/BRA/network.json). Neither is simulated.
 */
export function parseUpload(text: string, bytes: number, declared: string): UploadResult {
  if (bytes > MAX_BYTES) return fail(`El archivo pesa ${(bytes / 1024 / 1024).toLocaleString("es-CL", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MB; el máximo es ${MAX_BYTES / 1024 / 1024} MB.`);
  if (!isIso3(declared)) return fail("Indica el país de la red con un código ISO3 válido (por ejemplo, PER).");
  let doc: unknown;
  try { doc = JSON.parse(text); } catch { return fail("El archivo no es JSON válido."); }
  if (isObj(doc) && doc.type === "FeatureCollection" && Array.isArray(doc.features)) return _fromGeoJson(doc, declared);
  if (isObj(doc) && Array.isArray(doc.buses) && Array.isArray(doc.lines)) return _fromV1(doc, declared);
  return fail("Formato no reconocido: se espera un GeoJSON con subestaciones, líneas y centrales, o un archivo de red en JSON con barras y líneas.");
}

const fail = (...errors: string[]): UploadFail => ({ ok: false, errors });

class Checker {
  errors: string[] = [];
  extra = 0;
  add(message: string) { if (this.errors.length < MAX_ERRORS) this.errors.push(message); else this.extra++; }
  result(): string[] { return this.extra ? [...this.errors, `y ${fmt(this.extra)} errores más.`] : this.errors; }

  position(what: string, lon: unknown, lat: unknown): LonLat | null {
    if (typeof lon !== "number" || typeof lat !== "number" || !Number.isFinite(lon) || !Number.isFinite(lat)) { this.add(`${what}: coordenadas que no son números.`); return null; }
    if (lat < -90 || lat > 90) { this.add(`${what}: latitud ${lat} fuera de rango (−90 a 90).`); return null; }
    if (lon < -180 || lon > 180) { this.add(`${what}: longitud ${lon} fuera de rango (−180 a 180).`); return null; }
    return [lon, lat];
  }
  kv(what: string, v: unknown): number | null {
    if (typeof v !== "number" || !Number.isFinite(v)) { this.add(`${what}: la tensión (kv) no es un número.`); return null; }
    if (v < 1 || v > 1500) { this.add(`${what}: tensión de ${v} kV fuera de rango (1 a 1.500 kV).`); return null; }
    return v;
  }
  optionalNumber(what: string, field: string, v: unknown): number | null {
    if (v == null) return null;
    if (typeof v !== "number" || !Number.isFinite(v) || v < 0) { this.add(`${what}: ${field} debe ser un número mayor o igual a 0.`); return null; }
    return v;
  }
  id(what: string, v: unknown, seen: Set<string>): string | null {
    const id = typeof v === "string" || typeof v === "number" ? cleanText(v) : "";
    if (!id) { this.add(`${what}: falta el id.`); return null; }
    if (seen.has(id)) { this.add(`${what}: el id ${id} está repetido.`); return null; }
    seen.add(id);
    return id;
  }
}

interface Draft { subs: RegionalSubstation[]; lines: (RegionalLine & { a: string; b: string })[]; plants: (RegionalPlant & { bus: string | null })[] }

function _fromGeoJson(doc: Obj, iso: string): UploadResult {
  const features = doc.features as unknown[];
  const isLine = (f: unknown) => isObj(f) && isObj(f.geometry) && f.geometry.type === "LineString";
  const lineCount = features.filter(isLine).length;
  if (lineCount > MAX_LINES) return fail(`El archivo trae ${fmt(lineCount)} líneas; el máximo es ${fmt(MAX_LINES)}.`);
  if (features.length - lineCount > MAX_BUSES * 2) return fail(`El archivo trae ${fmt(features.length - lineCount)} puntos; el máximo es ${fmt(MAX_BUSES)} subestaciones (y otras tantas centrales).`);
  const c = new Checker();
  const draft: Draft = { subs: [], lines: [], plants: [] };
  const ids = { subs: new Set<string>(), lines: new Set<string>(), plants: new Set<string>() };
  const countries: unknown[] = [];
  features.forEach((f, i) => {
    if (!isObj(f) || !isObj(f.geometry)) return c.add(`Elemento ${i + 1}: no es un Feature con geometría.`);
    const p: Obj = isObj(f.properties) ? f.properties : {};
    countries.push(p.country);
    const g = f.geometry;
    const coords = g.coordinates;
    const source = cleanText(p.source) || DEFAULT_SOURCE;
    if (g.type === "LineString") {
      const what = label("Línea", i, p.id);
      const id = c.id(what, p.id, ids.lines);
      const kv = c.kv(what, p.kv);
      const path = Array.isArray(coords) && coords.length >= 2 ? coords.map((pt) => (Array.isArray(pt) ? c.position(what, pt[0], pt[1]) : null)) : null;
      if (!path) return c.add(`${what}: una línea necesita al menos dos puntos.`);
      const a = cleanText(p.a), b = cleanText(p.b);
      if (!a || !b) return c.add(`${what}: faltan los extremos a y b (ids de subestación).`);
      if (id == null || kv == null || path.some((x) => !x)) return;
      draft.lines.push({ id, country: iso, kv, a, b, circuits: c.optionalNumber(what, "circuits", p.circuits), lengthKm: c.optionalNumber(what, "length_km", p.length_km), source, path: path as LonLat[] });
    } else if (g.type === "Point") {
      const isPlant = p.bus != null || (p.mw != null && p.kv == null);
      const what = label(isPlant ? "Central" : "Subestación", i, p.id);
      const position = Array.isArray(coords) ? c.position(what, coords[0], coords[1]) : (c.add(`${what}: punto sin coordenadas.`), null);
      if (isPlant) {
        const id = c.id(what, p.id, ids.plants);
        const mw = c.optionalNumber(what, "mw", p.mw);
        if (p.mw == null) c.add(`${what}: falta la potencia (mw).`);
        if (id == null || mw == null || !position) return;
        draft.plants.push({ id, country: iso, name: cleanText(p.name), tech: cleanText(p.tech, 30) || null, mw, count: Math.max(1, Math.round(Number(p.count) || 1)), source, position, bus: cleanText(p.bus) || null });
      } else {
        const id = c.id(what, p.id, ids.subs);
        const kv = c.kv(what, p.kv);
        if (id == null || kv == null || !position) return;
        draft.subs.push({ id, country: iso, name: cleanText(p.name), kv, kind: cleanText(p.kind, 20) || "substation", source, position });
      }
    } else c.add(`Elemento ${i + 1}: geometría ${cleanText(g.type, 20) || "desconocida"} no admitida (solo Point y LineString).`);
  });
  return _finish(c, draft, "geojson", iso, countries, null);
}

function _fromV1(doc: Obj, iso: string): UploadResult {
  const buses = doc.buses as unknown[];
  const lines = [...(doc.lines as unknown[]), ...(Array.isArray(doc.dc_links) ? doc.dc_links : [])];
  if (buses.length > MAX_BUSES) return fail(`El archivo trae ${fmt(buses.length)} subestaciones; el máximo es ${fmt(MAX_BUSES)}.`);
  if (lines.length > MAX_LINES) return fail(`El archivo trae ${fmt(lines.length)} líneas; el máximo es ${fmt(MAX_LINES)}.`);
  const plants = Array.isArray(doc.plants) ? doc.plants : [];
  if (plants.length > MAX_BUSES) return fail(`El archivo trae ${fmt(plants.length)} grupos de centrales; el máximo es ${fmt(MAX_BUSES)}.`);
  const c = new Checker();
  const draft: Draft = { subs: [], lines: [], plants: [] };
  const ids = { subs: new Set<string>(), lines: new Set<string>(), plants: new Set<string>() };
  const countries: unknown[] = [doc.country];
  const docSource = Array.isArray(doc.sources) ? doc.sources.map((s) => (isObj(s) ? cleanText(s.name) : "")).find(Boolean) : isObj(doc.sources) ? cleanText(doc.sources.name) : "";
  buses.forEach((x, i) => {
    if (!isObj(x)) return c.add(`Subestación ${i + 1}: no es un objeto.`);
    countries.push(x.country);
    const what = label("Subestación", i, x.id);
    const id = c.id(what, x.id, ids.subs);
    const kv = c.kv(what, x.kv);
    const position = c.position(what, x.lon, x.lat);
    if (id == null || kv == null || !position) return;
    draft.subs.push({ id, country: iso, name: cleanText(x.name), kv, kind: "substation", source: cleanText(x.source) || docSource || DEFAULT_SOURCE, position });
  });
  const at = new Map(draft.subs.map((s) => [s.id, s.position]));
  lines.forEach((x, i) => {
    if (!isObj(x)) return c.add(`Línea ${i + 1}: no es un objeto.`);
    countries.push(x.country);
    const what = label("Línea", i, x.id);
    const id = c.id(what, x.id, ids.lines);
    const kv = c.kv(what, x.kv);
    const a = cleanText(x.a), b = cleanText(x.b);
    if (!a || !b) return c.add(`${what}: faltan los extremos a y b.`);
    if (id == null || kv == null) return;
    const pa = at.get(a), pb = at.get(b);
    draft.lines.push({ id, country: iso, kv, a, b, circuits: c.optionalNumber(what, "circuits", x.circuits), lengthKm: c.optionalNumber(what, "length_km", x.length_km),
      source: cleanText(x.source) || docSource || DEFAULT_SOURCE, path: pa && pb ? [pa, pb] : [] });
  });
  plants.forEach((x, i) => {
    if (!isObj(x)) return c.add(`Central ${i + 1}: no es un objeto.`);
    countries.push(x.country);
    const what = label("Central", i, x.id);
    const id = c.id(what, x.id, ids.plants);
    const mw = c.optionalNumber(what, "mw", x.mw);
    if (x.mw == null) c.add(`${what}: falta la potencia (mw).`);
    const bus = cleanText(x.bus);
    const position = at.get(bus);
    if (!bus) c.add(`${what}: falta la subestación (bus).`);
    if (id == null || mw == null || !bus) return;
    draft.plants.push({ id, country: iso, name: cleanText(x.name), tech: cleanText(x.tech, 30) || null, mw, count: Math.max(1, Math.round(Number(x.count) || 1)), source: cleanText(x.source) || docSource || DEFAULT_SOURCE, position: position ?? [0, 0], bus });
  });
  return _finish(c, draft, "v1", iso, countries, cleanText(isObj(doc) ? doc.name : null) || null);
}

/** Checks shared by both formats: line ends and plant buses name existing substations, and the file is not empty. */
function _finish(c: Checker, d: Draft, format: UploadFormat, iso: string, countries: unknown[], name: string | null): UploadResult {
  if (d.subs.length > MAX_BUSES) c.add(`El archivo trae ${fmt(d.subs.length)} subestaciones; el máximo es ${fmt(MAX_BUSES)}.`);
  const subs = new Set(d.subs.map((s) => s.id));
  d.lines.forEach((l) => {
    if (l.a === l.b) c.add(`Línea ${l.id}: sus dos extremos son la misma subestación (${l.a}).`);
    for (const end of [l.a, l.b]) if (!subs.has(end)) c.add(`Línea ${l.id}: el extremo ${end} no es una subestación del archivo.`);
  });
  d.plants.forEach((p) => { if (p.bus && !subs.has(p.bus)) c.add(`Central ${p.id}: la subestación ${p.bus} no está en el archivo.`); });
  if (!c.errors.length && !d.subs.length) c.add("El archivo no trae subestaciones.");
  if (c.errors.length) return { ok: false, errors: c.result() };
  const declaredInFile = countries.map((x) => cleanText(x, 3).toUpperCase()).filter(Boolean);
  const fileCountry = declaredInFile.find((x) => x !== iso) ?? null;
  const warnings = d.lines.length ? [] : ["El archivo no trae líneas: solo se dibujan las subestaciones."];
  return {
    ok: true, format, name, fileCountry, warnings,
    grid: {
      countries: [],
      substations: d.subs,
      lines: d.lines.map(({ a: _a, b: _b, ...l }) => l),
      plants: d.plants.map(({ bus: _bus, ...p }) => p),
    },
  };
}
