import { describe, expect, it } from "vitest";
import { changesOf, countEdits, dropChange, editKey, factorOf, fromCache, loadEdits, NO_EDITS, saveEdits, setFactor } from "./edits";
import { describeChange } from "./NetworkState";

const memory = () => {
  const data = new Map<string, string>();
  return { getItem: (k: string) => data.get(k) ?? null, setItem: (k: string, v: string) => void data.set(k, v), removeItem: (k: string) => void data.delete(k) };
};

describe("component factors", () => {
  it("writes one change per component and target, and 1 removes it", () => {
    let e = setFactor(NO_EDITS, "population", "B062", 2);
    e = setFactor(e, "population", "B062", 3);
    e = setFactor(e, "demand", "B062", 1.2);
    expect(changesOf(e)).toEqual([{ target: "population", buses: ["B062"], factor: 3 }, { target: "demand", buses: ["B062"], factor: 1.2 }]);
    expect(factorOf(e, "population", "B062")).toBe(3);
    expect(factorOf(setFactor(e, "population", "B062", 1), "population", "B062")).toBe(1);
    expect(factorOf(setFactor(NO_EDITS, "lines", "R239", 0.5), "lines", "R239")).toBe(0.5);
  });

  it("leaves the assistant's changes by filters alone", () => {
    const e = { ...NO_EDITS, changes: [{ target: "generation" as const, buses: ["B062"], tech: ["hidro"], factor: 0.5 }] };
    expect(factorOf(e, "generation", "B062")).toBe(1);
    expect(changesOf(setFactor(e, "generation", "B062", 2))).toHaveLength(2);
  });

  it("a prepared scenario is never read from the cache and changes the simulation key", () => {
    const e = setFactor({ lines: ["R239"], buses: [] }, "population", "B062", 2);
    expect(fromCache({ lines: ["R239"], buses: [] })).toBe(true);
    expect(fromCache(e)).toBe(false);
    expect(editKey("p", e)).not.toBe(editKey("p", { lines: ["R239"], buses: [] }));
    expect(countEdits(dropChange(e, 0))).toBe(1);
  });

  it("keeps the changes across a reload", () => {
    const store = memory();
    const e = setFactor(NO_EDITS, "demand", "B001", 1.5);
    saveEdits(e, store);
    expect(loadEdits(store)).toEqual(e);
    saveEdits(NO_EDITS, store);
    expect(loadEdits(store)).toEqual(NO_EDITS);
  });
});

describe("describeChange", () => {
  it("says what, how much and where", () => {
    const name = (id: string) => (id === "B062" ? "Cerro Navia" : id);
    expect(describeChange({ target: "population", buses: ["B062"], factor: 2 }, name, (x) => x)).toBe("Personas × 2 · Cerro Navia");
    expect(describeChange({ target: "generation", tech: ["hidro"], factor: 0.5 }, name, (x) => x)).toBe("Generación × 0.5 · hidro");
    expect(describeChange({ target: "demand", add: 200 }, name, (x) => x)).toBe("Demanda +200 MW · todo el país");
  });
});
