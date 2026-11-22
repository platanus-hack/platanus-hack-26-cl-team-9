import type { SimulationResult } from "./gridsApi";
import type { Edits } from "./edits";
import { countEdits } from "./edits";
import { formatPeople, int, lineName, placeName } from "./text";
import type { Network, Timeline } from "./types";

/**
 * Tab "Estado de la red": every change made to the grid, kept together so that a new cut adds to the others and
 * never replaces them. Each one can be put back alone, or all at once.
 */
export function NetworkState({ network, edits, result, timeline, restoreLine, restoreBus, restoreAll }: {
  network: Network; edits: Edits; result: SimulationResult | null; timeline: Timeline | null;
  restoreLine(id: string): void; restoreBus(id: string): void; restoreAll(): void;
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
      <CascadeLines network={network} timeline={timeline} />
      {result && edits.buses.length > 0 && (
        <p className="meta">Apagar {edits.buses.length === 1 ? "esa subestación" : "esas subestaciones"} deja sin suministro a {formatPeople(result.direct.people)} personas y quita {int(result.direct.load_mw)} MW de demanda y {int(result.direct.gen_mw)} MW de generación, antes de la cascada.</p>
      )}
      {result?.warnings.map((w) => <p className="note" key={w.code + w.message}>{w.message}</p>)}
      <p className="source">Con una sola línea se lee la simulación precalculada; con más cambios la calcula el motor en el servidor, todos juntos.</p>
    </>
  );
}

/** Lines the cascade opened by itself (overload over 120 %), apart from the ones the user cut, with the second they opened. */
function CascadeLines({ network, timeline }: { network: Network; timeline: Timeline | null }) {
  const opened = (timeline?.events ?? []).filter((e) => e.type === "line_overload_open").flatMap((e) => e.ids.map((id) => ({ id, t: e.t })));
  const collapsed = (timeline?.events ?? []).filter((e) => e.type === "island_blackout");
  if (!opened.length && !collapsed.length) return null;
  return (
    <div className="card state-list">
      <div className="card-head"><div className="title"><h3>Consecuencias en la red · {opened.length + collapsed.length}</h3></div></div>
      {opened.length > 0 && <div className="list-head"><span>Líneas abiertas por sobrecarga · {opened.length}</span><span>segundo</span></div>}
      {opened.map(({ id, t }) => (
        <div className="state-row" key={id}><span className="ellipsis" title={lineName(network, id)}>{lineName(network, id)}</span><span className="num">{t.toFixed(1)} s</span></div>
      ))}
      {collapsed.length > 0 && <div className="list-head"><span>Islas apagadas · {collapsed.length}</span><span>segundo</span></div>}
      {collapsed.map((e, k) => (
        <div className="state-row" key={k}><span className="ellipsis">{int(Number(e.params.buses))} subestaciones, {int(Number(e.params.load_mw))} MW · {REASON[String(e.params.reason)] ?? String(e.params.reason)}</span><span className="num">{e.t.toFixed(1)} s</span></div>
      ))}
      <p className="meta">Estas no las cortaste tú: las abre el motor cuando una línea supera el 120 % de su capacidad, o se apagan cuando una isla pierde la frecuencia o la tensión.</p>
    </div>
  );
}

const REASON: Record<string, string> = {
  voltage: "colapso por tensión", frequency: "frecuencia bajo 47,5 Hz", no_generation: "sin generación", no_load: "sin demanda", no_inertia: "sin inercia",
};
