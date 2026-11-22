import { describe, expect, it } from "vitest";
import { DEFAULT_POINT, syncedSearch } from "./url";

const base = { pointId: DEFAULT_POINT, cut: null, mode: "2d" as const, sid: null };

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
  it("writes the 3D view", () => {
    expect(syncedSearch("", { ...base, mode: "3d" })).toBe("?vista=3d");
  });
  it("keeps the session, drops point and cut, keeps vista", () => {
    const out = syncedSearch("?sesion=abc&point=feb2025-1500&cut=R239", {
      pointId: "feb2025-1500", cut: "R239", mode: "3d", sid: "abc",
    });
    expect(out).toBe("?sesion=abc&vista=3d");
  });
  it("keeps unrelated params", () => {
    expect(syncedSearch("?mapa=3", base)).toBe("?mapa=3");
  });
  it("normalises an explicit default point away", () => {
    expect(syncedSearch("?point=nov2026-1300", base)).toBe("");
  });
});
