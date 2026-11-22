import type { Prepared } from "../cascade/gridsApi";
import { EventHealth, PrefaultHealth } from "../cascade/SimulationPanel";
import { formatPeople, int } from "../cascade/text";
import type { HealthReport, Timeline } from "../cascade/types";

/**
 * Asistente → "Salud de la red": how the grid on the map stands after the assistant's (or the user's) changes. With
 * failures it reads the simulated cascade; with changes only, the prepared grid (POST /grids/prepare); otherwise the
 * base point. Every figure comes from the backend; the index is our model's, not a CEN indicator (docs/health.md).
 */
export function GridHealth({ prepared, timeline, failures, base }: {
  prepared: Prepared | null; timeline: Timeline | null; failures: boolean; base: HealthReport | null;
}) {
  const cascade = failures ? timeline : null;
  const totals = prepared?.totals;
  const health = cascade?.health ? null : prepared?.health ?? base;
  return (
    <div className="card">
      <div className="card-head"><h3>Salud de la red</h3></div>
      <p className="meta">{cascade ? "Red con los cambios y las fallas, al final de la simulación." : prepared ? "Red con los cambios, antes de cualquier falla." : "Red base del punto de operación, sin cambios."}</p>
      <div className="mini-figures ruled">
        {totals && <div><div className="value-row"><b>{int(totals.load_total_mw)} MW</b></div><span>demanda</span></div>}
        {totals && <div><div className="value-row"><b>{int(totals.gen_total_mw)} MW</b></div><span>generación</span></div>}
        {prepared && <div><div className="value-row"><b>{prepared.overloaded_lines.length}</b></div><span>líneas sobre su límite</span></div>}
        {cascade && <div><div className="value-row"><b>{formatPeople(cascade.summary.people_without_power)}</b></div><span>personas sin suministro</span></div>}
        {cascade && <div><div className="value-row"><b>{int(cascade.summary.load_shed_mw)} MW</b></div><span>carga perdida</span></div>}
        {cascade && <div><div className="value-row"><b>{cascade.summary.lines_opened.length}</b></div><span>líneas que salieron</span></div>}
      </div>
      {cascade?.health && <EventHealth timeline={cascade} />}
      {health && <PrefaultHealth health={health} />}
      {!cascade && !prepared && !base && <p className="meta">Aún no hay datos de salud para esta red.</p>}
    </div>
  );
}
