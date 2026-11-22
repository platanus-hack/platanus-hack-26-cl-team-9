import { useEffect, useState } from "react";
import { loadOutageCost, type OutageCost, type SimulationResult } from "./gridsApi";
import { impactAt } from "./simulation";
import type { Edits } from "./edits";
import { countEdits } from "./edits";
import { formatPeople, int, lineName, pct, placeName } from "./text";
import type { BusState, Network, Timeline } from "./types";
import { Info } from "./ui";

/**
 * Tab "Estado de la red": every change made to the grid, kept together so that a new cut adds to the others and
 * never replaces them. Each one can be put back alone, or all at once.
 */
export function NetworkState({ network, buses, point, edits, result, timeline, restoreLine, restoreBus, restoreAll }: {
  network: Network; buses: Record<string, BusState>; point: string; edits: Edits; result: SimulationResult | null; timeline: Timeline | null;
  restoreLine(id: string): void; restoreBus(id: string): void; restoreAll(): void;
}) {
  const total = countEdits(edits);
  if (total === 0) {
    return (
      <div className="card empty">
        <h3>Sin cambios</h3>
        <p>La red está como en el punto de operación elegido. Haz clic en una línea o una subestación del mapa para ver su detalle, y clic otra vez para sacarla de servicio o apagarla. Cada cambio se suma a los anteriores y queda en esta lista.</p>
      </div>
    );
  }
  const dropped = new Set(result?.dropped_lines ?? []);
  const ready = timeline && timeline.events.length > 0 ? timeline : null;
  const nodeName = (id: string) => placeName(network.nodes.find((n) => n.id === id)?.name ?? id);
  return (
    <>
      {ready && <Outcome timeline={ready} buses={buses} point={point} edits={edits} />}
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

/**
 * Final result of the cascade, read with the same `impactAt` the Simulación tab uses at its last second, so both tabs give
 * the same figures. The cost comes from the backend (`POST /grids/cost`): total, per hour of outage, and blackout or load shedding.
 */
function Outcome({ timeline, buses, point, edits }: { timeline: Timeline; buses: Record<string, BusState>; point: string; edits: Edits }) {
  const end = impactAt(timeline, buses, timeline.duration_s);
  const dark = timeline.events.filter((e) => e.type === "island_blackout").length;
  const cost = useOutageCost(point, edits);
  return (
    <div className="card impact">
      <div className="card-head">
        <div className="title"><h3>Resultado de la caída</h3><Info tip="Estado final de la red tras la cascada, calculado por el motor Sub50 con todos los cambios de esta lista. Es la misma cifra que Simulación muestra al final." /></div>
        <span className="share">{pct(end.share)} del país</span>
      </div>
      <div className="people">{int(end.people)}</div>
      <p className="meta">personas sin suministro</p>
      <div className="mini-figures ruled">
        <div><div className="value-row"><b>{int(end.lostLoadMw)} <small>MW</small></b></div><span>de {int(timeline.summary.load_total_mw)} MW de demanda</span></div>
        <div><div className="value-row"><b>{int(end.lostGenMw)} <small>MW</small></b></div><span>generación perdida</span></div>
        <div><div className="value-row"><b>{dark}</b></div><span>{dark === 1 ? "isla apagada" : "islas apagadas"}</span></div>
      </div>
      <CostRow cost={cost} />
    </div>
  );
}

/** Total and per hour, and whether it is a total blackout (black start) or load shedding in a grid that holds. */
function CostRow({ cost }: { cost: CostState }) {
  if (cost.state !== "ready" || !cost.value) {
    return <p className="meta">{cost.state === "error" ? cost.error : cost.state === "loading" ? "Calculando el costo…" : "Costo de la caída: el servidor aún no lo calcula."}</p>;
  }
  const c = cost.value;
  const kind = c.breakdown.dark_mw <= 0 ? "corte parcial de carga (EDAC)" : c.breakdown.dark_share >= 0.9 ? "apagón total" : "apagón parcial";
  const tip = [`Costo de falla CNE ${int(c.unserved_cost_usd_per_mwh.value / 1000)} US$/kWh`, ...c.assumptions].join(" · ");
  return (
    <div className="mini-figures ruled">
      <div><div className="value-row"><b>US$ {formatPeople(c.cost_usd)}</b><Info tip={tip} /></div><span>costo de la caída</span></div>
      <div><div className="value-row"><b>US$ {formatPeople(c.cost_per_hour_usd)}</b></div><span>por hora de corte</span></div>
      <div><div className="value-row"><b>{int(c.energy_not_served_mwh)} <small>MWh</small></b></div><span>{kind} · {c.outage_hours.value} h</span></div>
    </div>
  );
}

type CostState = { state: "loading" | "ready" | "pending" | "error"; value: OutageCost | null; error?: string };

function useOutageCost(point: string, edits: Edits): CostState {
  const [cost, setCost] = useState<CostState>({ state: "loading", value: null });
  const key = `${point}|${edits.lines.join(",")}|${edits.buses.join(",")}`;
  useEffect(() => {
    let live = true;
    setCost({ state: "loading", value: null });
    loadOutageCost({ point, open_lines: edits.lines, out_buses: edits.buses })
      .then((value) => live && setCost({ state: value ? "ready" : "pending", value }))
      .catch((e) => live && setCost({ state: "error", value: null, error: String(e.message) }));
    return () => { live = false; };
  }, [key]);
  return cost;
}
