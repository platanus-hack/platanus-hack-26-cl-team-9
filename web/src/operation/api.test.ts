import { describe, expect, it } from "vitest";
import { CachedSource, LiveSource, connect } from "./api";

const json = (data: unknown, ok = true) => Promise.resolve({ ok, status: ok ? 200 : 404, json: () => Promise.resolve(data) } as Response);

describe("connect", () => {
  it("uses the live API when /health answers", async () => {
    const src = await connect(((url: string) => (url.endsWith("/health") ? json({}) : json({}, false))) as typeof fetch);
    expect(src).toBeInstanceOf(LiveSource);
    expect(src.live).toBe(true);
  });

  it("falls back to the offline cache when the backend is down", async () => {
    const src = await connect((() => Promise.reject(new Error("down"))) as typeof fetch);
    expect(src).toBeInstanceOf(CachedSource);
    expect(src.live).toBe(false);
  });
});

describe("CachedSource", () => {
  const run = {
    run: { run_id: "x", template: "flagship_observability", policy: "C", operating_point: "nov2026-1300", seed: 7 },
    snapshots: [0, 1, 2].map((cycle) => ({ cycle, t_min: cycle * 5 })),
    report: {}, after_action: {},
  };
  const files: Record<string, unknown> = {
    "/cache/theater/index.json": { points: ["nov2026-1300"], runs: [{ file: "nov2026-1300/f-C-s7.json", point: "nov2026-1300", template: "flagship_observability", policy: "C", seed: 7 }] },
    "/cache/theater/nov2026-1300/f-C-s7.json": run,
  };
  const fetcher = ((url: string) => (url in files ? json(files[url]) : json({}, false))) as typeof fetch;

  it("plays the precomputed snapshots in order and finishes", async () => {
    const src = new CachedSource(fetcher);
    const summary = await src.create({ template: "flagship_observability", policy: "C", point: "nov2026-1300" });
    const a = await src.step(summary.run_id, 2);
    expect(a.snapshots.map((s) => s.cycle)).toEqual([0, 1]);
    expect(a.run.status).toBe("running");
    const b = await src.step(summary.run_id, 2);
    expect(b.snapshots.map((s) => s.cycle)).toEqual([2]);
    expect(b.run.status).toBe("finished");
  });

  it("refuses to inject events offline", async () => {
    await expect(new CachedSource(fetcher).inject()).rejects.toThrow(/Sin servidor/);
  });
});
