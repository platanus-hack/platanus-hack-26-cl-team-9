import { describe, expect, it } from "vitest";
import { addBus, addLine, countEdits, dropBus, dropLine, editKey, fromCache, loadEdits, NO_EDITS, parseFactor, saveEdits, scenarioEdits, startEdits } from "./edits";

describe("edits", () => {
  it("keeps every change, not only the last one", () => {
    const e = addBus(addLine(addLine(NO_EDITS, "R001"), "R002"), "B010");
    expect(e).toEqual({ lines: ["R001", "R002"], buses: ["B010"] });
    expect(countEdits(e)).toBe(3);
  });

  it("ignores a change that is already in the list", () => {
    expect(addLine(addLine(NO_EDITS, "R001"), "R001").lines).toEqual(["R001"]);
    expect(addBus(addBus(NO_EDITS, "B001"), "B001").buses).toEqual(["B001"]);
  });

  it("restores one change and leaves the others", () => {
    const e = { lines: ["R001", "R002"], buses: ["B010"] };
    expect(dropLine(e, "R001")).toEqual({ lines: ["R002"], buses: ["B010"] });
    expect(dropBus(e, "B010")).toEqual({ lines: ["R001", "R002"], buses: [] });
  });

  it("reads the cache only for zero or one line", () => {
    expect(fromCache(NO_EDITS)).toBe(true);
    expect(fromCache({ lines: ["R001"], buses: [] })).toBe(true);
    expect(fromCache({ lines: ["R001", "R002"], buses: [] })).toBe(false);
    expect(fromCache({ lines: [], buses: ["B001"] })).toBe(false);
  });

  it("gives the same key whatever the order of the changes", () => {
    expect(editKey("p", { lines: ["R2", "R1"], buses: [] })).toBe(editKey("p", { lines: ["R1", "R2"], buses: [] }));
    expect(editKey("p", NO_EDITS)).not.toBe(editKey("q", NO_EDITS));
  });
});

describe("saved changes", () => {
  const memory = () => { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k), m }; };

  it("keeps the changes across a reload and forgets them when they are all put back", () => {
    const store = memory();
    saveEdits({ lines: ["R239"], buses: ["B020"] }, store);
    expect(loadEdits(store)).toEqual({ lines: ["R239"], buses: ["B020"] });
    saveEdits(NO_EDITS, store);
    expect(store.m.size).toBe(0);
    expect(loadEdits(store)).toEqual(NO_EDITS);
  });

  it("ignores what it cannot read", () => {
    const store = memory();
    store.setItem("sub50.edits.v1", "{not json");
    expect(loadEdits(store)).toEqual(NO_EDITS);
    store.setItem("sub50.edits.v1", JSON.stringify({ lines: ["R1", 3], buses: "x" }));
    expect(loadEdits(store)).toEqual({ lines: ["R1"], buses: [] });
  });
});

describe("start of the page (F-14)", () => {
  const stored = { lines: ["R001", "R002"], buses: ["B010"] };
  it("starts clean without a cut in the URL and offers the saved changes", () => {
    expect(startEdits(null, stored)).toEqual({ edits: NO_EDITS, restorable: stored });
    expect(startEdits(null, NO_EDITS)).toEqual({ edits: NO_EDITS, restorable: null });
  });
  it("takes the link's line or substation as the only change", () => {
    expect(startEdits("R239", stored)).toEqual({ edits: { lines: ["R239"], buses: [] }, restorable: null });
    expect(startEdits("sub-B012", stored)).toEqual({ edits: { lines: [], buses: ["B012"] }, restorable: null });
  });
});

describe("card factors (A2-02)", () => {
  it("never reads a blank field as 0", () => {
    expect(parseFactor("", "lines")).toHaveProperty("error");
    expect(parseFactor("  ", "population")).toHaveProperty("error");
    expect(parseFactor("abc", "demand")).toHaveProperty("error");
  });
  it("keeps the backend's bounds: over 0 for a line's capacity, 0 to 5 otherwise", () => {
    expect(parseFactor("0", "lines")).toEqual({ error: "Escribe un número mayor que 0 y hasta 5." });
    expect(parseFactor("0", "generation")).toEqual({ factor: 0 });
    expect(parseFactor("5,5", "demand")).toEqual({ error: "Escribe un número entre 0 y 5." });
    expect(parseFactor("-1", "population")).toHaveProperty("error");
    expect(parseFactor("1,5", "lines")).toEqual({ factor: 1.5 });
  });
});

describe("scenarioEdits", () => {
  it("a condition starts with nothing off, and a disaster with only its own failures", () => {
    expect(scenarioEdits(null)).toEqual(NO_EDITS);
    const own = { lines: ["R1"], buses: ["B2"] };
    const fresh = scenarioEdits(own);
    expect(fresh).toEqual(own);
    expect(fresh.lines).not.toBe(own.lines); // a copy: later cuts never write into the scenario's list
  });
});
