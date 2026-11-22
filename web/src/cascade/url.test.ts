import { describe, expect, it } from "vitest";
import { DEFAULT_POINT, syncedSearch } from "./url";

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
    expect(syncedSearch(`?point=${DEFAULT_POINT}`, base)).toBe("");
  });
  it("writes a network other than Chile's, and drops ?pais=CHL", () => {
    expect(syncedSearch("", { ...base, country: "PER" })).toBe("?pais=PER");
    expect(syncedSearch("?pais=CHL", { ...base, country: "CHL" })).toBe("");
  });
  it("a session is always Chile's: no pais", () => {
    expect(syncedSearch("?sesion=abc&pais=PER", { ...base, sid: "abc", country: "PER" })).toBe("?sesion=abc");
  });
});
