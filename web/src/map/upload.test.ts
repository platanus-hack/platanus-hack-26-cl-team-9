import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { regionalTooltip } from "./regional";
import { cleanText, MAX_BUSES, MAX_BYTES, MAX_TEXT, parseUpload, type UploadFail, type UploadOk } from "./upload";

const sub = (id: string, lon: number, lat: number, extra: object = {}) => ({ type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: { id, name: `SE ${id}`, kv: 220, kind: "substation", source: "prueba", ...extra } });
const line = (id: string, a: string, b: string, extra: object = {}) => ({ type: "Feature", geometry: { type: "LineString", coordinates: [[-70, -33], [-71, -34]] }, properties: { id, a, b, kv: 220, circuits: 1, length_km: 120, source: "prueba", ...extra } });
const plant = (id: string, bus: string, extra: object = {}) => ({ type: "Feature", geometry: { type: "Point", coordinates: [-70, -33] }, properties: { id, bus, name: "Central", mw: 150, tech: "solar", count: 2, source: "prueba", ...extra } });
const geo = (features: object[]) => JSON.stringify({ type: "FeatureCollection", features });
const VALID = geo([sub("A", -70, -33), sub("B", -71, -34), line("L1", "A", "B"), plant("G1", "A")]);
const v1 = (patch: object = {}) => JSON.stringify({
  version: 1, country: "PER", buses: [{ id: "PER-A", name: "A", lat: -12, lon: -77, kv: 220 }, { id: "PER-B", name: "B", lat: -13, lon: -76, kv: 220 }],
  lines: [{ id: "PER-L1", a: "PER-A", b: "PER-B", kv: 220, circuits: 1, length_km: 150, x_pu: 0.05, capacity_mw: 300 }], dc_links: [], plants: [{ id: "PER-G1", bus: "PER-A", mw: 90, tech: "hidro", count: 1 }], ...patch,
});
const parse = (text: string, iso = "PER") => parseUpload(text, text.length, iso);
const ok = (text: string, iso = "PER") => { const r = parse(text, iso); if (!r.ok) throw new Error(r.errors.join(" | ")); return r as UploadOk; };
const errors = (text: string, iso = "PER", bytes = text.length) => (parseUpload(text, bytes, iso) as UploadFail).errors?.join(" | ") ?? "";

describe("parseUpload accepts", () => {
  it("a GeoJSON in the regional schema, writing the declared country on every element", () => {
    const r = ok(VALID);
    expect(r.format).toBe("geojson");
    expect([r.grid.substations.length, r.grid.lines.length, r.grid.plants.length]).toEqual([2, 1, 1]);
    expect([...r.grid.substations, ...r.grid.lines, ...r.grid.plants].every((x) => x.country === "PER")).toBe(true);
    expect(r.fileCountry).toBeNull();
  });
  it("the v1 network JSON, drawing each line between its buses", () => {
    const r = ok(v1());
    expect(r.format).toBe("v1");
    expect(r.grid.lines[0].path).toEqual([[-77, -12], [-76, -13]]);
    expect(r.grid.plants[0].position).toEqual([-77, -12]);
  });
  it("Brazil's real network.json and Peru's three drawn layers merged into one file", () => {
    const bra = readFileSync("../data/processed/latam/BRA/network.json", "utf8");
    const r = ok(bra, "BRA");
    expect(r.grid.substations.length).toBeGreaterThan(800);
    const per = ["lines", "substations", "plants"].flatMap((l) => JSON.parse(readFileSync(`../data/processed/latam/PER/${l}.geojson`, "utf8")).features);
    expect(ok(geo(per)).grid.lines.length).toBeGreaterThan(200);
  });
});

describe("parseUpload refuses, saying what failed", () => {
  it("a file over the size limit, before parsing it", () => {
    expect(errors("{", "PER", MAX_BYTES + 1)).toMatch(/máximo es 10 MB/);
  });
  it("an invalid or missing country", () => {
    expect(errors(VALID, "XYZ")).toMatch(/ISO3/);
    expect(errors(VALID, "")).toMatch(/ISO3/);
    expect(errors(VALID, "per")).toMatch(/ISO3/);
  });
  it("text that is not JSON, and JSON of an unknown shape", () => {
    expect(errors("<html>")).toMatch(/no es JSON válido/);
    expect(errors(JSON.stringify({ hello: 1 }))).toMatch(/Formato no reconocido/);
    expect(errors("[1,2]")).toMatch(/Formato no reconocido/);
  });
  it("coordinates outside the planet", () => {
    expect(errors(geo([sub("A", -70, -91), sub("B", -71, -34), line("L1", "A", "B")]))).toMatch(/latitud -91 fuera de rango/);
    expect(errors(geo([sub("A", 200, -33), sub("B", -71, -34)]))).toMatch(/longitud 200 fuera de rango/);
    expect(errors(geo([sub("A", "x" as unknown as number, -33)]))).toMatch(/no son números/);
  });
  it("voltages and powers that are not numbers or out of range", () => {
    expect(errors(geo([sub("A", -70, -33, { kv: "220" })]))).toMatch(/tensión \(kv\) no es un número/);
    expect(errors(geo([sub("A", -70, -33, { kv: 5000 })]))).toMatch(/fuera de rango/);
    expect(errors(geo([sub("A", -70, -33), plant("G1", "A", { mw: -5 })]))).toMatch(/mw debe ser un número/);
  });
  it("line ends that are not substations of the file, or the same one twice", () => {
    expect(errors(geo([sub("A", -70, -33), sub("B", -71, -34), line("L1", "A", "Z")]))).toMatch(/extremo Z no es una subestación/);
    expect(errors(geo([sub("A", -70, -33), line("L1", "A", "A")]))).toMatch(/misma subestación/);
    expect(errors(v1({ lines: [{ id: "L", a: "PER-A", b: "PER-X", kv: 220 }] }))).toMatch(/extremo PER-X/);
    expect(errors(geo([sub("A", -70, -33), line("L1", "", "A")]))).toMatch(/faltan los extremos/);
  });
  it("repeated ids, too many buses, and a file with no substations", () => {
    expect(errors(geo([sub("A", -70, -33), sub("A", -71, -34)]))).toMatch(/id A está repetido/);
    const buses = Array.from({ length: MAX_BUSES + 1 }, (_, i) => ({ id: `B${i}`, name: "x", lat: 0, lon: 0, kv: 220 }));
    expect(errors(v1({ buses, lines: [] }))).toMatch(/máximo es 5\.000/);
    expect(errors(geo([]))).toMatch(/no trae subestaciones/);
  });
  it("caps a long list of errors", () => {
    const bad = Array.from({ length: 40 }, (_, i) => sub(`S${i}`, -70, -95));
    expect(errors(geo(bad))).toMatch(/errores más/);
  });
});

describe("parseUpload country check", () => {
  it("reports a file that names another country so the user confirms", () => {
    expect(ok(v1(), "BOL").fileCountry).toBe("PER");
    expect(ok(geo([sub("A", -70, -33, { country: "CHL" }), sub("B", -71, -34)]), "PER").fileCountry).toBe("CHL");
    expect(ok(v1(), "PER").fileCountry).toBeNull();
  });
});

describe("untrusted text", () => {
  const evil = '<img src=x onerror="alert(1)"><script>alert(2)</script>';
  it("keeps a malicious name as literal, short text and never runs it", () => {
    const r = ok(geo([sub("A", -70, -33, { name: evil + "x".repeat(500) }), sub("B", -71, -34), line("L1", "A", "B", { source: evil })]));
    const name = r.grid.substations[0].name;
    expect(name.startsWith("<img src=x")).toBe(true); // literal characters: React and the tooltip's `text` show them as typed
    expect(name.length).toBe(MAX_TEXT);
    // The tooltip is plain text (deck.gl `text`, never `html`): the string is passed through unchanged, not turned into markup.
    expect(regionalTooltip("regional-substations", r.grid.substations[0])).toContain("<img src=x");
    expect(regionalTooltip("regional-lines", r.grid.lines[0])).toContain("<script>");
  });
  it("drops control characters and never copies unknown fields", () => {
    expect(cleanText("a\u0000b\u001fc\u007f d")).toBe("a b c d");
    expect(cleanText({ toString: () => "x" })).toBe("");
    const r = ok(geo([sub("A", -70, -33, { __proto__: { polluted: true }, onclick: "x" }), sub("B", -71, -34)]));
    expect(Object.keys(r.grid.substations[0]).sort()).toEqual(["country", "id", "kind", "kv", "name", "position", "source"]);
    expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  });
});
