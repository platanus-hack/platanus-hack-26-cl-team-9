import { Fragment, useEffect, useState } from "react";
import { conditionDate, conditionName, cutName as nameOfCut } from "./text";
import type { Network, PointInfo } from "./types";
import { Chevron } from "./ui";

/** The 25F reference case: the 500 kV corridor cut, opened by default at the February 2025 15:00 operating point. */
export const CASE_25F = { point: "feb2025-1500", cut: "R239" };

type Key = "25f" | "custom" | "new";
interface Row { key: Key; name: string; title?: string; cut: string | null; year?: number; faint?: boolean }
export interface ScenarioChoice { point: string; cut: string | null }

/**
 * "Escenarios" in the nav rail as a two-level tree (Paper Design v6, docs/design.md 3.3). A scenario is a cut; each one
 * lists the operating conditions it can run under. The active condition of the active scenario carries the selection.
 * `cuts` holds the open lines (one outside a session, any number in one). `locked` (the tip text) is set in a shared
 * session, which pins its operating point: rows only expand and collapse, and the conditions are disabled.
 */
export function ScenarioTree({ points, pointId, cuts, network, open, locked }: {
  points: PointInfo[]; pointId: string; cuts: string[]; network: Network | null; open(next: ScenarioChoice): void; locked?: string;
}) {
  const cut = cuts[0] ?? null;
  const active: Key = cuts.length === 1 && cut === CASE_25F.cut ? "25f" : cut ? "custom" : "new";
  const year = points.find((p) => p.id === pointId)?.year;
  const [expanded, setExpanded] = useState<Set<Key>>(() => new Set([active]));
  // A scenario that becomes active (from the rail, a map click or the URL) opens; collapsing it again is up to the user.
  useEffect(() => { setExpanded((s) => (s.has(active) ? s : new Set(s).add(active))); }, [active]);

  const names = cuts.map((id) => (network ? nameOfCut(network, id) : id));
  const cutName = names.join(", ");
  const rows: Row[] = [
    { key: "25f", name: "Apagón 25F", cut: CASE_25F.cut, year: active === "25f" ? year : 2025 },
    ...(active === "custom" ? [{ key: "custom" as const, name: `Corte ${names.map((n) => n.replace(/ \(.*\)$/, "")).join(", ")}`, title: cutName, cut, year }] : []),
    { key: "new", name: "Escenario nuevo", cut: null, faint: active !== "new" },
  ];

  function toggle(key: Key) {
    setExpanded((s) => { const next = new Set(s); if (next.has(key)) next.delete(key); else next.add(key); return next; });
  }

  function clickRow(row: Row) {
    if (row.key === active || locked) return toggle(row.key);
    setExpanded((s) => new Set(s).add(row.key));
    open({ point: row.key === "25f" ? CASE_25F.point : pointId, cut: row.cut });
  }

  return (
    <div className="scenarios">
      {rows.map((row) => {
        const on = row.key === active;
        const isOpen = expanded.has(row.key);
        const id = `scenario-${row.key}-conditions`;
        return (
          <Fragment key={row.key}>
            <button className={on ? "scenario on" : row.faint ? "scenario faint" : "scenario"} aria-expanded={isOpen} aria-controls={isOpen ? id : undefined}
              title={row.title} onClick={() => clickRow(row)}>
              <span className="disclosure"><Chevron dir={isOpen ? "down" : "right"} color="currentColor" /></span>
              <span className="ellipsis">{row.name}</span>
              {row.year != null && <span className="year">{row.year}</span>}
            </button>
            {isOpen && (
              <div className="conditions" id={id} role="group" aria-label={`Condiciones de operación: ${row.name}`}>
                {points.map((p) => {
                  const current = on && p.id === pointId;
                  return (
                    <button key={p.id} className={current ? "condition on" : "condition"} aria-current={current || undefined} title={locked ? undefined : p.label}
                      aria-disabled={locked && !current ? "true" : undefined} data-tip={locked} onClick={() => !locked && open({ point: p.id, cut: row.cut })}>
                      <span className="cond-name ellipsis">{conditionName(p.label)}</span>
                      <span className="cond-date">{conditionDate(p.snapshot)}</span>
                    </button>
                  );
                })}
              </div>
            )}
          </Fragment>
        );
      })}
    </div>
  );
}
