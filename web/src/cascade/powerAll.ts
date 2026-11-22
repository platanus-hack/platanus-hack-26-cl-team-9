/**
 * "Prender todo": one step back to the full, energised network at the same operating point. Pure, so it can be tested
 * without the shell. In a session the shell also repairs every open line through the API (CascadeApp.tsx).
 */
import type { Pick } from "./clicks";

/** What the button looks at: the cuts in force (local or the session's open lines) and whether anything was edited. */
export interface PowerAllState { cuts: readonly string[]; edited: boolean }

/** The part of the shell state that "Prender todo" resets. */
export interface PowerAllView { pointId: string; cut: string | null; selection: Pick | null; t: number; playing: boolean }

/**
 * Enabled when something is switched off or edited. A selection or a timeline position alone does not enable it.
 * `edited` is always false for now; #42 phase B (local value edits) plugs in here.
 */
export function canPowerAll({ cuts, edited }: PowerAllState): boolean {
  return cuts.length > 0 || edited;
}

/** Same operating point, no cut, no selection, timeline at 0 and paused: the base case of that hour. */
export function powerAll(view: PowerAllView): PowerAllView {
  return { pointId: view.pointId, cut: null, selection: null, t: 0, playing: false };
}
