import { useState } from "react";
import type { Edits } from "./edits";
import { conditionDate, conditionName } from "./text";
import type { PointInfo } from "./types";
import { Chevron } from "./ui";

/** A real disaster replayed on the model: an operating point and the changes it applies (lines cut, substations out). */
/** `date`: when the real event happened, shown instead of the date of the hour it runs on (the analogues run in 2026). */
export interface Disaster { id: string; name: string; point: string; edits: Edits; title: string; date?: string }

/**
 * Desastres (docs/escenarios.md). Only the 25F runs on its own hour; 2010 and 2011 are analogues on today's network at
 * the closest hour we have (the 2026 evening peak), not reproductions.
 */
export const DISASTERS: Disaster[] = [
  {
    id: "25f", name: "Apagón 25F", point: "feb2025-1500", edits: { lines: ["R239"], buses: [] },
    title: "25 feb 2025: corte del corredor de 500 kV Nueva Maitencillo – Nueva Pan de Azúcar",
  },
  {
    id: "2011", name: "Apagón 2011 · Ancoa", point: "nov2026-2000", edits: { lines: ["R006"], buses: [] }, date: "24 sep 2011 · 20:31",
    title: "Análogo del 24 sep 2011 (falla de un transformador 500/220 kV en S/E Ancoa, 9,8 M personas): corte de Alto Jahuel – Ancoa 500 kV en la punta nocturna de 2026",
  },
  {
    id: "2010", name: "Terremoto 2010 · Charrúa", point: "nov2026-2000", edits: { lines: [], buses: ["B043"] }, date: "14 mar 2010 · 20:43",
    title: "Análogo del 14 mar 2010 (transformador de S/E Charrúa dañado por el terremoto del 27F, apagón de todo el SIC): S/E Charrúa fuera de servicio en la punta nocturna de 2026",
  },
];

/** The 25F reference case, the one a bare link with `?cut=R239` stands for. */
export const CASE_25F = { point: DISASTERS[0].point, cut: DISASTERS[0].edits.lines[0] };

/** `edits` replaces the user's changes (a disaster); null keeps them (a Benchmark condition, only the hour changes). */
export interface ScenarioChoice { point: string; edits: Edits | null }

type Folder = "desastres" | "benchmark";
const same = (a: string[], b: string[]) => a.length === b.length && [...a].sort().join() === [...b].sort().join();

/** The disaster the grid is showing right now: same hour and exactly its changes. */
export function activeDisaster(pointId: string, edits: Edits): Disaster | null {
  return DISASTERS.find((d) => d.point === pointId && same(d.edits.lines, edits.lines) && same(d.edits.buses, edits.buses)) ?? null;
}

/**
 * "Escenarios" in the nav rail as two folders. Desastres replays real events; Benchmark holds the operating conditions,
 * which are the base cases the user edits. The cuts the user makes are not scenarios: they live in "Estado de la red".
 * Benchmark lists every condition except the 25F's own hour, which is its Desastres entry. `locked` (the tip text) is
 * set in a shared session, which pins its operating point: the folders only expand and collapse, and the entries are
 * disabled.
 */
export function ScenarioTree({ points, pointId, edits, open, locked }: {
  points: PointInfo[]; pointId: string; edits: Edits; open(next: ScenarioChoice): void; locked?: string;
}) {
  const [expanded, setExpanded] = useState<Set<Folder>>(new Set(["desastres", "benchmark"]));
  const disaster = activeDisaster(pointId, edits);
  const benchmark = points.filter((p) => p.id !== CASE_25F.point);
  const dateOf = (point: string) => conditionDate(points.find((p) => p.id === point)?.snapshot);

  const toggle = (f: Folder) => setExpanded((s) => { const next = new Set(s); if (next.has(f)) next.delete(f); else next.add(f); return next; });
  const entry = (key: string, name: string, date: string, on: boolean, choice: ScenarioChoice, title?: string) => (
    <button key={key} className={on ? "condition on" : "condition"} aria-current={on || undefined} title={locked ? undefined : title}
      aria-disabled={locked && !on ? "true" : undefined} data-tip={locked && !on ? locked : undefined} onClick={() => !locked && open(choice)}>
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
      {folder("desastres", "Desastres", DISASTERS.map((d) =>
        entry(d.id, d.name, d.date ?? dateOf(d.point), disaster?.id === d.id, { point: d.point, edits: d.edits }, d.title)))}
      {folder("benchmark", "Benchmark", benchmark.map((p) =>
        entry(p.id, conditionName(p.label), conditionDate(p.snapshot), !disaster && p.id === pointId, { point: p.id, edits: null }, p.label)))}
    </div>
  );
}
