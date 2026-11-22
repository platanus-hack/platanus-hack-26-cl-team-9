import { describe, expect, it } from "vitest";
import { interpretClick, NO_CLICK, pickOf, type ClickAction, type Pick } from "./clicks";

const A: Pick = { kind: "line", id: "R001" };
const B: Pick = { kind: "line", id: "R002" };
const NODE: Pick = { kind: "node", id: "B010" };

/**
 * Feeds a sequence of [target, tapCount, ms] callbacks and returns the actions. The selection follows the app:
 * select sets it, toggle clears it (cutLine and the substation switch-off clear it), clear clears it.
 */
function run(clicks: [Pick | null, number, number][], selected: Pick | null = null): ClickAction[] {
  let memory = NO_CLICK;
  let selection = selected;
  return clicks.map(([target, taps, at]) => {
    const out = interpretClick(target, taps, at, selection, memory);
    memory = out.memory;
    if (out.action.type === "select") selection = out.action.target;
    else if (out.action.type !== "none") selection = null;
    return out.action;
  });
}
const toggles = (actions: ClickAction[]) => actions.filter((a) => a.type === "toggle");

describe("map click interpretation", () => {
  it("selects a line on a single click, without waiting", () => {
    expect(run([[A, 1, 0]])).toEqual([{ type: "select", target: A }]);
  });

  it("switches the selected line off on a slow second click", () => {
    expect(run([[A, 1, 0], [A, 1, 1000]])).toEqual([{ type: "select", target: A }, { type: "toggle", target: A }]);
  });

  it("never switches off on a Mapbox double click (click, click, dblclick)", () => {
    const actions = run([[A, 1, 0], [A, 1, 180], [A, 2, 181]]);
    expect(actions).toEqual([{ type: "select", target: A }, { type: "none" }, { type: "none" }]);
  });

  it("never switches off on an offline double click (tapCount 1, 2) or a triple tap", () => {
    expect(run([[A, 1, 0], [A, 2, 200]])).toEqual([{ type: "select", target: A }, { type: "none" }]);
    expect(toggles(run([[A, 1, 0], [A, 2, 200], [A, 3, 380]]))).toHaveLength(0);
  });

  it("switches off once on a slow second click followed by the OS dblclick, and does not select the line again", () => {
    const actions = run([[A, 1, 0], [A, 1, 450], [A, 2, 451]]);
    expect(actions).toEqual([{ type: "select", target: A }, { type: "toggle", target: A }, { type: "none" }]);
  });

  it("ignores a tapCount 2 on the selected element even without a remembered first click", () => {
    expect(run([[A, 2, 0]], A)).toEqual([{ type: "none" }]);
  });

  it("switches off with one map click when the selection came from the panel", () => {
    expect(run([[A, 1, 5000]], A)).toEqual([{ type: "toggle", target: A }]);
  });

  it("selects a different element instead of switching off, even with tapCount 2", () => {
    expect(run([[A, 1, 0], [B, 1, 150], [B, 2, 151]])).toEqual([{ type: "select", target: A }, { type: "select", target: B }, { type: "none" }]);
    expect(run([[A, 1, 0], [B, 2, 200]])).toEqual([{ type: "select", target: A }, { type: "select", target: B }]);
  });

  it("switches a substation off on a slow second click, never on a double click", () => {
    expect(run([[NODE, 1, 0], [NODE, 1, 900]])).toEqual([{ type: "select", target: NODE }, { type: "toggle", target: NODE }]);
    expect(toggles(run([[NODE, 1, 0], [NODE, 1, 100], [NODE, 2, 101]]))).toHaveLength(0);
  });

  it("clears the selection on a click on nothing", () => {
    expect(run([[A, 1, 0], [null, 1, 1000]])[1]).toEqual({ type: "clear" });
  });

  it("selects the same element again after a click on nothing", () => {
    expect(run([[A, 1, 0], [null, 1, 100], [A, 1, 200]])[2]).toEqual({ type: "select", target: A });
  });
});

describe("picked object", () => {
  it("reads lines, dashed open lines, substations and demand", () => {
    expect(pickOf("lines", { id: "R001" })).toEqual(A);
    expect(pickOf("lines-open", { line: { id: "R001" }, path: [] })).toEqual(A);
    expect(pickOf("nodes", { id: "B010" })).toEqual(NODE);
    expect(pickOf("load-2d", { id: "B010" })).toEqual(NODE);
    expect(pickOf("regional-lines", { id: "ARG-R1" })).toBeNull();
    expect(pickOf("lines", null)).toBeNull();
  });
});
