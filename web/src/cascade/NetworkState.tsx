import type { SimulationResult } from "./gridsApi";
import type { Edits } from "./edits";
import { countEdits } from "./edits";
import { formatPeople, int, lineName, placeName } from "./text";
import type { Network } from "./types";

/**
 * Tab "Estado de la red": every change made to the grid, kept together so that a new cut adds to the others and
 * never replaces them. Each one can be put back alone, or all at once.
 */
export function NetworkState({ network, edits, result, restoreLine, restoreBus, restoreAll }: {
  network: Network; edits: Edits; result: SimulationResult | null; restoreLine(id: string): void; restoreBus(id: string): void; restoreAll(): void;
}) {
  const total = countEdits(edits);
  if (total === 0) {
    return (
      <div className="card empty">
        <h3>Sin cambios</h3>
        <p>La red está como en el punto de operación elegido. Haz doble clic en una línea del mapa para sacarla de servicio, o en una subestación para apagarla. Cada cambio se suma a los anteriores y queda en esta lista.</p>
      </div>
    );
  }
  const dropped = new Set(result?.dropped_lines ?? []);
  const nodeName = (id: string) => placeName(network.nodes.find((n) => n.id === id)?.name ?? id);
  return (
    <>
      <div className="card state-list">
        <div className="card-head">
          <div className="title"><h3>Cambios en la red · {total}</h3></div>
          <button className="text-btn" onClick={restoreAll}>Reponer todo</button>
        </div>
        {edits.lines.length > 0 && <div className="list-head"><span>Líneas fuera de servicio · {edits.lines.length}</span></div>}
        {edits.lines.map((id) => (
          <div className="state-row" key={id}>
            <span className="ellipsis" title={lineName(network, id)}>{lineName(network, id)}{dropped.has(id) ? " · sale con su subestación" : ""}</span>
            <button className="text-btn" onClick={() => restoreLine(id)}>Reponer</button>
          </div>
        ))}
        {edits.buses.length > 0 && <div className="list-head"><span>Subestaciones fuera de servicio · {edits.buses.length}</span></div>}
        {edits.buses.map((id) => (
          <div className="state-row" key={id}>
            <span className="ellipsis">{nodeName(id)}</span>
            <button className="text-btn" onClick={() => restoreBus(id)}>Reponer</button>
          </div>
        ))}
      </div>
      {result && edits.buses.length > 0 && (
        <p className="meta">Apagar {edits.buses.length === 1 ? "esa subestación" : "esas subestaciones"} deja sin suministro a {formatPeople(result.direct.people)} personas y quita {int(result.direct.load_mw)} MW de demanda y {int(result.direct.gen_mw)} MW de generación, antes de la cascada.</p>
      )}
      {result?.warnings.map((w) => <p className="note" key={w.code + w.message}>{w.message}</p>)}
      <p className="source">Con una sola línea se lee la simulación precalculada; con más cambios la calcula el motor en el servidor, todos juntos.</p>
    </>
  );
}
