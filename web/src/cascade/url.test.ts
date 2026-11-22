import { describe, expect, it } from "vitest";
import { DEFAULT_POINT, resolvePoint, syncedSearch, urlCutOf } from "./url";
import { NO_EDITS } from "./edits";

const base = { pointId: DEFAULT_POINT, cut: null, sid: null };

describe("syncedSearch", () => {
  it("gives an empty search on defaults", () => {
    expect(syncedSearch("", base)).toBe("");
  });
  it("writes a non-default point", () => {
    expect(syncedSearch("", { ...base, pointId: "feb2025-1500" })).toBe("?point=feb2025-1500");
  });
  it("writes a cut", () => {
    expect(syncedSearch("", { ...base, cut: "R239" })).toBe("?cut=R239");
  });
  it("drops an old 3D view param", () => {
    expect(syncedSearch("?vista=3d", base)).toBe("");
  });
  it("keeps the session, drops point and cut", () => {
    const out = syncedSearch("?sesion=abc&point=feb2025-1500&cut=R239&vista=3d", {
      pointId: "feb2025-1500", cut: "R239", sid: "abc",
    });
    expect(out).toBe("?sesion=abc");
  });
  it("keeps unrelated params", () => {
    expect(syncedSearch("?mapa=3", base)).toBe("?mapa=3");
  });
  it("normalises an explicit default point away", () => {
    expect(syncedSearch("?point=nov2026-1300", base)).toBe("");
  });
  it("writes a network other than Chile's, and drops ?pais=CHL", () => {
    expect(syncedSearch("", { ...base, country: "PER" })).toBe("?pais=PER");
    expect(syncedSearch("?pais=CHL", { ...base, country: "CHL" })).toBe("");
  });
  it("a session is always Chile's: no pais", () => {
    expect(syncedSearch("?sesion=abc&pais=PER", { ...base, sid: "abc", country: "PER" })).toBe("?sesion=abc");
  });
});

describe("URL of the changes", () => {
  it("writes one line or one substation shutdown, nothing else (A-03)", () => {
    expect(urlCutOf(NO_EDITS)).toBeNull();
    expect(urlCutOf({ lines: ["R239"], buses: [] })).toBe("R239");
    expect(urlCutOf({ lines: [], buses: ["B012"] })).toBe("sub-B012");
    expect(urlCutOf({ lines: ["R1", "R2"], buses: [] })).toBeNull();
    expect(urlCutOf({ lines: ["R1"], buses: ["B1"] })).toBeNull();
    expect(urlCutOf({ lines: ["R1"], buses: [], changes: [{ target: "demand", buses: ["B1"], factor: 2 }] })).toBeNull();
  });
  it("falls back to the default point when the link names an unknown one (A-01)", () => {
    expect(resolvePoint("xxx", ["nov2026-1300", "feb2025-1500"])).toEqual({ pointId: DEFAULT_POINT, unknown: "xxx" });
    expect(resolvePoint("feb2025-1500", ["nov2026-1300", "feb2025-1500"])).toEqual({ pointId: "feb2025-1500", unknown: null });
    expect(resolvePoint(null, [])).toEqual({ pointId: DEFAULT_POINT, unknown: null });
  });
});
