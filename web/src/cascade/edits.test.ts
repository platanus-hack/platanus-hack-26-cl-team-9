import { describe, expect, it } from "vitest";
import { addBus, addLine, countEdits, dropBus, dropLine, editKey, fromCache, NO_EDITS } from "./edits";

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
