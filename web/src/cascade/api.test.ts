import { afterEach, describe, expect, it, vi } from "vitest";
import { loadHealth } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("loadHealth", () => {
  it("returns null when the cache predates health.json", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("not found", { status: 404 })));
    await expect(loadHealth("old-point")).resolves.toBeNull();
  });
  it("returns null when the host answers a missing file with the SPA page", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html></html>", { status: 200, headers: { "content-type": "text/html" } })));
    await expect(loadHealth("spa-point")).resolves.toBeNull();
  });
});
