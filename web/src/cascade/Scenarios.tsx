import { useState } from "react";
import { countEdits, type Edits } from "./edits";
import { conditionDate, conditionName } from "./text";
import type { PointInfo } from "./types";
import { Chevron } from "./ui";

/** A real disaster replayed on the model: an operating point and the changes it applies (lines cut, substations out). */
/**
 * `date`: when the real event happened, shown instead of the date of the hour it runs on (the analogues run in 2026).
 * `real`: the real event's figure, shown next to the model's while the entry is active, with its source in the tip.
 */
export interface Disaster { id: string; name: string; point: string; edits: Edits; title: string; date?: string; real?: { text: string; tip: string } }

/**
 * Desastres (docs/escenarios.md). Only the 25F runs on its own hour; 2010 and 2011 are analogues on today's network at
 * the closest hour we have (the 2026 evening peak), not reproductions. The real figures come from docs/mapa3.md section 4.
 */
export const DISASTERS: Disaster[] = [
  {
    id: "25f", name: "Apagón 25F", point: "feb2025-1500", edits: { lines: ["R239"], buses: [] }, date: "25 feb 2025 · 15:16",
    title: "25 feb 2025: corte del corredor de 500 kV Nueva Maitencillo – Nueva Pan de Azúcar",
    real: {
      text: "Evento real: unos 19 M de personas (98,5 %)",
      tip: "Cifra aproximada del apagón real del 25 feb 2025, de Arica a Chiloé, entregada por el equipo; el informe del Coordinador Eléctrico Nacional sobre el 25F describe el evento. La simulación corre en una red resumida, así que no tiene por qué coincidir.",
    },
  },
  {
    id: "2011", name: "Apagón 2011 · Ancoa", point: "nov2026-2000", edits: { lines: ["R006"], buses: [] }, date: "24 sep 2011 · 20:31",
    title: "Análogo del 24 sep 2011 (falla de un transformador 500/220 kV en S/E Ancoa, 9,8 M personas): corte de Alto Jahuel – Ancoa 500 kV en la punta nocturna de 2026",
    real: {
      text: "Análogo en la red de 2026. Evento real: 9,8 M de personas",
      tip: "Apagón del 24 sep 2011, de Coquimbo al Maule, por la falla de un transformador 500/220 kV en S/E Ancoa (Wikipedia, «Apagón de Chile de 2011»). Aquí se simula un análogo en la red de 2026, no una reproducción.",
    },
  },
  {
    id: "2010", name: "Terremoto 2010 · Charrúa", point: "nov2026-2000", edits: { lines: [], buses: ["B043"] }, date: "14 mar 2010 · 20:43",
    title: "Análogo del 14 mar 2010 (transformador de S/E Charrúa dañado por el terremoto del 27F, apagón de todo el SIC): S/E Charrúa fuera de servicio en la punta nocturna de 2026",
    real: {
      text: "Análogo en la red de 2026. Evento real: más de 13 M de personas",
      tip: "Apagón de todo el SIC del 14 mar 2010, tras el daño del terremoto del 27F en un transformador de S/E Charrúa (prensa de la época). Aquí se simula un análogo en la red de 2026, no una reproducción.",
    },
  },
];

/** The 25F reference case, the one a bare link with `?cut=R239` stands for. */
export const CASE_25F = { point: DISASTERS[0].point, cut: DISASTERS[0].edits.lines[0] };

/** `edits` replaces the user's changes (a disaster); null keeps them (an operating condition, only the hour changes). */
export interface ScenarioChoice { point: string; edits: Edits | null }

/** The folder the user picked from last: after picking a condition, the condition is highlighted even when the kept changes match a disaster. */
export type ScenarioKind = "disaster" | "condition";

type Folder = "desastres" | "condiciones";
const same = (a: string[], b: string[]) => a.length === b.length && [...a].sort().join() === [...b].sort().join();

/**
 * "Apagón 2011 · Ancoa" as parts that wrap as a whole. Each part after the first carries its own separator, and the
 * separator of a part that starts a line falls outside the row and is clipped (cascade.css `.name-parts`), so no line
 * starts or ends with a lone dot.
 */
function nameParts(name: string) {
  const parts = name.split(" · ");
  if (parts.length < 2) return name;
  return <span className="name-parts">{parts.map((x, i) => <span key={i} className="name-part">{x}</span>)}</span>;
}

/** The disaster the grid is showing right now: same hour and exactly its changes. */
export function activeDisaster(pointId: string, edits: Edits): Disaster | null {
  return DISASTERS.find((d) => d.point === pointId && same(d.edits.lines, edits.lines) && same(d.edits.buses, edits.buses)) ?? null;
}

/** "Con 1 cambio tuyo" under the active condition, so the rail says the changes stayed when only the hour changed. */
export const keptNote = (changes: number) => (changes === 1 ? "Con 1 cambio tuyo" : `Con ${changes} cambios tuyos`);

/**
 * "Escenarios" in the nav rail as two folders. Desastres replays real events; "Condiciones de operación" (shown as
 * "Condiciones", the full name does not fit the row) holds the
 * operating conditions, which are the base cases the user edits. The cuts the user makes are not scenarios: they live in
 * the Cambios tab. The conditions list every point except the 25F's own hour, which is its Desastres entry. `locked`
 * (the tip text) is set in a shared session, which pins its operating point: the folders only expand and collapse, and
 * the entries are disabled. `pointId` is null while a view-only network is shown: then no entry is highlighted. `last`
 * is the folder the user picked from last. The active condition says when changes are in force (they are kept).
 */
export function ScenarioTree({ points, pointId, edits, open, locked, last = "disaster" }: {
  points: PointInfo[]; pointId: string | null; edits: Edits; open(next: ScenarioChoice): void; locked?: string; last?: ScenarioKind;
}) {
  const [expanded, setExpanded] = useState<Set<Folder>>(new Set(["desastres", "condiciones"]));
  const disaster = pointId && last === "disaster" ? activeDisaster(pointId, edits) : null;
  const changes = countEdits(edits);
  const conditions = points.filter((p) => p.id !== CASE_25F.point);
  const dateOf = (point: string) => conditionDate(points.find((p) => p.id === point)?.snapshot);

  const toggle = (f: Folder) => setExpanded((s) => { const next = new Set(s); if (next.has(f)) next.delete(f); else next.add(f); return next; });
  const entry = (key: string, name: string, date: string, on: boolean, choice: ScenarioChoice, title?: string, note?: string) => (
    <button key={key} className={on ? "condition on" : "condition"} aria-current={on || undefined} title={locked ? undefined : title}
      aria-disabled={locked && !on ? "true" : undefined} data-tip={locked && !on ? locked : undefined} onClick={() => !locked && open(choice)}>
      <span className="cond-name">{nameParts(name)}</span>
      <span className="cond-date">{date}</span>
      {note && <span className="cond-note">{note}</span>}
    </button>
  );
  // `full` names the folder for assistive tech and the tip when the visible name is shortened to fit the 13 px row.
  const folder = (key: Folder, name: string, children: React.ReactNode, full = name) => {
    const isOpen = expanded.has(key);
    return (
      <>
        <button className="scenario" aria-expanded={isOpen} aria-controls={isOpen ? `scenarios-${key}` : undefined} aria-label={full} title={full === name ? undefined : full} onClick={() => toggle(key)}>
          <span className="disclosure"><Chevron dir={isOpen ? "down" : "right"} color="currentColor" /></span>
          <span className="scenario-name">{name}</span>
        </button>
        {isOpen && <div className="conditions" id={`scenarios-${key}`} role="group" aria-label={full}>{children}</div>}
      </>
    );
  };

  return (
    <div className="scenarios">
      {folder("desastres", "Desastres", DISASTERS.map((d) =>
        entry(d.id, d.name, d.date ?? dateOf(d.point), disaster?.id === d.id, { point: d.point, edits: d.edits }, d.title)))}
      {/* "Condiciones de operación" does not fit the rail row at 13 px (D6), so the row reads "Condiciones". */}
      {folder("condiciones", "Condiciones", conditions.map((p) => {
        const on = !disaster && p.id === pointId;
        return entry(p.id, conditionName(p.label), conditionDate(p.snapshot), on, { point: p.id, edits: null }, p.label, on && changes > 0 ? keptNote(changes) : undefined);
      }), "Condiciones de operación")}
    </div>
  );
}
