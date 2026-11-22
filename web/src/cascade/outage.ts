import type { Pick } from "./clicks";
import type { Edits } from "./edits";
import { substationLines } from "./text";
import type { Network } from "./types";

/** Lines per `POST /{sid}/cut` call (`CutIn`, docs/sessions-api.md). */
export const CUT_BATCH = 3;

/**
 * Whether the user has switched a line or substation off. `edits` holds the session's open lines (and no buses), or the
 * local changes without a session.
 * - Session: a line is off when it is open; a substation when it has lines and all of them are open.
 * - No session: a line is off when it is in `edits.lines`; a substation when it is in `edits.buses`.
 */
export function isSwitchedOff(pick: Pick, network: Network, edits: Edits, session: boolean): boolean {
  if (pick.kind === "line") return edits.lines.includes(pick.id);
  if (!session) return edits.buses.includes(pick.id);
  const lines = substationLines(network, pick.id);
  return lines.length > 0 && lines.every((id) => edits.lines.includes(id));
}

/** Splits ids into groups of at most `size`, for an API that takes a few at a time. */
export function batches<T>(ids: readonly T[], size = CUT_BATCH): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < ids.length; i += size) out.push(ids.slice(i, i + size));
  return out;
}
