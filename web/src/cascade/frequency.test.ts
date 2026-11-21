import { describe, expect, it } from "vitest";
import { describeBalance, describeCurves, describeOutcome } from "./frequency";
import type { Event } from "./types";

const full = (f: number): [number, number][] => Array.from({ length: 101 }, (_, i) => [3 + i * 0.2, f]);
const formed = (curve: string, buses: number, gen: number, load: number): Event => ({ t: 3, type: "island_formed", ids: [], text_key: "island_formed", params: { buses, gen_mw: gen, load_mw: load, curve } });

describe("frequency chart legend", () => {
  it("tells a collapsed deficit island from a stable surplus island, with its balance", () => {
    const falling: [number, number][] = [[3, 50], [6, 49], [10.6, 47.5]];
    const rising = full(50.5).map((p, i) => [p[0], 50 + Math.min(i / 100, 0.56)] as [number, number]);
    const curves = describeCurves({ I1: rising, I2: falling }, [formed("I1", 105, 7653, 6256), formed("I2", 83, 3443, 4840)]);
    expect(curves.map((c) => c.letter)).toEqual(["A", "B"]);
    expect(curves[0].collapsed).toBe(false);
    expect(curves[1].collapsed).toBe(true);
    expect(describeOutcome(curves[1])).toContain("se apaga a los 10,6 s");
    expect(describeOutcome(curves[0])).toContain("sube hasta");
    expect(describeBalance(curves[1])).toBe("83 subestaciones, le faltan 1.397 MW");
    expect(describeBalance(curves[0])).toBe("105 subestaciones, le sobran 1.397 MW");
  });

  it("pairs untagged islands with curves in order, only when direction and start agree (older cache)", () => {
    const rising = full(50.5);
    const falling: [number, number][] = [[3, 50], [6, 49], [10.6, 47.5]];
    const untagged = (g1: number, l1: number) => [
      { t: 0, type: "island_formed", ids: [], text_key: "island_formed", params: { buses: 188, gen_mw: 11096, load_mw: 11096 } },
      { t: 3, type: "island_formed", ids: [], text_key: "island_formed", params: { buses: 105, gen_mw: g1, load_mw: l1 } },
      { t: 3, type: "island_formed", ids: [], text_key: "island_formed", params: { buses: 83, gen_mw: 3443, load_mw: 4840 } },
    ] as Event[];
    const ok = describeCurves({ I1: rising, I2: falling }, untagged(7653, 6256));
    expect(describeBalance(ok[1])).toBe("83 subestaciones, le faltan 1.397 MW");
    const wrong = describeCurves({ I1: rising, I2: falling }, untagged(6256, 7653)); // direction disagrees: no guess
    expect(describeBalance(wrong[0])).toBe("");
  });

  it("still describes the outcome when the island is not tagged (older cache)", () => {
    const [c] = describeCurves({ I1: full(50) }, []);
    expect(describeBalance(c)).toBe("");
    expect(describeOutcome(c)).toBe("se mantiene en 50 Hz");
  });
});
