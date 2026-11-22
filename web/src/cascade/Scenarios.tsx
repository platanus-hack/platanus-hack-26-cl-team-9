import { useState } from "react";
import { conditionDate, conditionName, lineName } from "./text";
import type { Network, PointInfo } from "./types";
import { Chevron } from "./ui";

/** The 25F reference case: the 500 kV corridor cut, opened at the February 2025 15:00 operating point. */
export const CASE_25F = { point: "feb2025-1500", cut: "R239" };

type Folder = "desastres" | "benchmark";
export interface ScenarioChoice { point: string; cut: string | null }

/**
 * "Escenarios" in the nav rail as two folders. Desastres holds the cuts (the 25F, and the cut the user makes on the map);
 * Benchmark holds the operating conditions with no cut, which are the base cases to compare against. The 25F's own
 * operating point is the Desastres entry, so Benchmark lists the other conditions. `cuts` holds the open lines (one
 * outside a session, any number in one). `locked` (the tip text) is set in a shared session, which pins its operating
 * point: folders only expand and collapse, and the entries are disabled.
 */
export function ScenarioTree({ points, pointId, cuts, network, open, locked }: {
  points: PointInfo[]; pointId: string; cuts: string[]; network: Network | null; open(next: ScenarioChoice): void; locked?: string;
}) {
  const [expanded, setExpanded] = useState<Set<Folder>>(new Set(["desastres", "benchmark"]));
  const current = points.find((p) => p.id === pointId);
  const is25f = cuts.length === 1 && cuts[0] === CASE_25F.cut;
  const custom = cuts.length > 0 && !is25f;
  const customName = network ? cuts.map((id) => lineName(network, id).replace(/ \(.*\)$/, "")).join(", ") : cuts.join(", ");
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
        {custom && entry("custom", `Corte ${customName}`, conditionDate(current?.snapshot), true, null, customName)}
      </>)}
      {folder("benchmark", "Benchmark", benchmark.map((p) =>
        entry(p.id, conditionName(p.label), conditionDate(p.snapshot), cuts.length === 0 && p.id === pointId, { point: p.id, cut: null }, p.label)))}
    </div>
  );
}
