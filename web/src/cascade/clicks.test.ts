import { describe, expect, it } from "vitest";
import { interpretClick, NO_CLICK, pickOf, type ClickAction, type Pick } from "./clicks";

const A: Pick = { kind: "line", id: "R001" };
const B: Pick = { kind: "line", id: "R002" };
const NODE: Pick = { kind: "node", id: "B010" };

/** Feeds a sequence of [target, tapCount, ms] callbacks and returns the actions. */
function run(clicks: [Pick | null, number, number][]): ClickAction[] {
  let memory = NO_CLICK;
  return clicks.map(([target, taps, at]) => {
    const out = interpretClick(target, taps, at, memory);
    memory = out.memory;
    return out.action;
  });
}
const cuts = (actions: ClickAction[]) => actions.filter((a) => a.type === "cut");

describe("map click interpretation", () => {
  it("selects a line on a single click, without waiting", () => {
    expect(run([[A, 1, 0]])).toEqual([{ type: "select", target: A }]);
  });

  it("cuts once on a Mapbox double click (click, click, dblclick)", () => {
    const actions = run([[A, 1, 0], [A, 1, 180], [A, 2, 181]]);
    expect(actions[0]).toEqual({ type: "select", target: A });
    expect(cuts(actions)).toEqual([{ type: "cut", id: "R001" }]);
  });

  it("cuts once when the OS double-click time is longer than ours (dblclick does the cut)", () => {
    const actions = run([[A, 1, 0], [A, 1, 450], [A, 2, 451]]);
    expect(actions).toEqual([{ type: "select", target: A }, { type: "select", target: A }, { type: "cut", id: "R001" }]);
  });

  it("cuts once on an offline double click (tapCount 1, 2) and ignores a third tap", () => {
    expect(run([[A, 1, 0], [A, 2, 200]])).toEqual([{ type: "select", target: A }, { type: "cut", id: "R001" }]);
    expect(cuts(run([[A, 1, 0], [A, 2, 200], [A, 3, 380]]))).toHaveLength(1);
  });

  it("does not cut on two slow clicks", () => {
    expect(cuts(run([[A, 1, 0], [A, 1, 1000]]))).toHaveLength(0);
  });

  it("does not cut on clicks on two different lines, even with tapCount 2", () => {
    const actions = run([[A, 1, 0], [B, 1, 150], [B, 2, 151]]);
    expect(cuts(actions)).toHaveLength(0);
    expect(actions[1]).toEqual({ type: "select", target: B });
  });

  it("does not cut when an offline tapCount 2 lands on another line than the first tap", () => {
    expect(run([[A, 1, 0], [B, 2, 200]])).toEqual([{ type: "select", target: A }, { type: "select", target: B }]);
  });

  it("selects a substation and never cuts it", () => {
    expect(run([[NODE, 1, 0], [NODE, 1, 100], [NODE, 2, 101]]).every((a) => a.type === "select")).toBe(true);
  });

  it("clears the selection on a click on nothing", () => {
    expect(run([[A, 1, 0], [null, 1, 1000]])[1]).toEqual({ type: "clear" });
  });

  it("can cut the same line again after a later double click", () => {
    expect(cuts(run([[A, 1, 0], [A, 2, 150], [A, 1, 2000], [A, 2, 2150]]))).toHaveLength(2);
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
