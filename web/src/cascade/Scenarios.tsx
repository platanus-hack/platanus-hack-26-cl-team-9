import { useState } from "react";
import { conditionDate, conditionName } from "./text";
import type { PointInfo } from "./types";
import { Chevron } from "./ui";

/** The 25F reference case: the 500 kV corridor cut, opened at the February 2025 15:00 operating point. */
export const CASE_25F = { point: "feb2025-1500", cut: "R239" };

type Folder = "desastres" | "benchmark";
/** `cut` is the line the scenario opens with; a Benchmark condition has none and keeps the user's changes. */
export interface ScenarioChoice { point: string; cut: string | null }

/**
 * "Escenarios" in the nav rail as two folders. Desastres holds the 25F; Benchmark holds the operating conditions, which
 * are the base cases the user edits. The cuts the user makes are not scenarios: they live in "Estado de la red".
 * The 25F's own operating point is the Desastres entry, so Benchmark lists the other conditions. `is25f` is set when the
 * only change is the 25F cut. `locked` (the tip text) is set in a shared session, which pins its operating point: the
 * folders only expand and collapse, and the entries are disabled.
 */
export function ScenarioTree({ points, pointId, is25f, open, locked }: {
  points: PointInfo[]; pointId: string; is25f: boolean; open(next: ScenarioChoice): void; locked?: string;
}) {
  const [expanded, setExpanded] = useState<Set<Folder>>(new Set(["desastres", "benchmark"]));
  const benchmark = points.filter((p) => p.id !== CASE_25F.point);

  const toggle = (f: Folder) => setExpanded((s) => { const next = new Set(s); if (next.has(f)) next.delete(f); else next.add(f); return next; });
  const entry = (key: string, name: string, date: string, on: boolean, choice: ScenarioChoice | null, title?: string) => (
    <button key={key} className={on ? "condition on" : "condition"} aria-current={on || undefined} title={locked ? undefined : title}
      aria-disabled={locked && !on ? "true" : undefined} data-tip={locked && !on ? locked : undefined} onClick={() => !locked && choice && open(choice)}>
      <span className="cond-name ellipsis">{name}</span>
      <span className="cond-date">{date}</span>
    </button>
  );
  const folder = (key: Folder, name: string, children: React.ReactNode) => {
    const isOpen = expanded.has(key);
    return (
      <>
        <button className="scenario" aria-expanded={isOpen} aria-controls={isOpen ? `scenarios-${key}` : undefined} onClick={() => toggle(key)}>
          <span className="disclosure"><Chevron dir={isOpen ? "down" : "right"} color="currentColor" /></span>
          <span className="ellipsis">{name}</span>
        </button>
        {isOpen && <div className="conditions" id={`scenarios-${key}`} role="group" aria-label={name}>{children}</div>}
      </>
    );
  };

  return (
    <div className="scenarios">
      {folder("desastres", "Desastres", <>
        {entry("25f", "Apagón 25F", conditionDate(points.find((p) => p.id === CASE_25F.point)?.snapshot), is25f, CASE_25F, "Corte del corredor de 500 kV Alto Jahuel–Ancoa")}
      </>)}
      {folder("benchmark", "Benchmark", benchmark.map((p) =>
        entry(p.id, conditionName(p.label), conditionDate(p.snapshot), !is25f && p.id === pointId, { point: p.id, cut: null }, p.label)))}
    </div>
  );
}
