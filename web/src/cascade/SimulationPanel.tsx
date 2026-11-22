import { useEffect, useRef } from "react";
import { withstandsAt, type Impact, type IslandFrequency } from "./simulation";
import { cutName, hz, int, narrate, pct, secs, shutdownNode } from "./text";
import type { Network, Timeline } from "./types";
import { Chevron, Info } from "./ui";

interface Props {
  network: Network; timeline: Timeline; cuts: string[]; t: number; impact: Impact; islands: IslandFrequency[]; totalPeople: number;
  seek(t: number): void; openSources(): void; restore(): void; source: string;
}

/** Tab "Simulación" (Design v5, V2 and V3): people without supply, lost load, and the numbered event history. */
export function SimulationPanel(p: Props) {
  const assumptions = p.timeline.assumptions.length;
  return (
    <>
      {p.cuts.length > 0 ? <ImpactCard {...p} /> : <EmptyCard />}
      {p.cuts.length > 0 && <History {...p} />}
      {p.timeline.truncated && <p className="note">La cascada llegó al tope de 20 etapas: el resultado puede ser mayor.</p>}
      <button className="assumptions-row" onClick={p.openSources}>
        <Info tip="Supuestos del motor que afectan esta simulación. Ábrelos para ver cada uno." />
        <span>{assumptions} supuestos en esta simulación</span>
        <Chevron dir="right" />
      </button>
      <p className="source">Fuente: IDE Energía, simulación Sub50. {p.source}</p>
    </>
  );
}

function EmptyCard() {
  return (
    <div className="card empty">
      <h3>Escenario nuevo</h3>
      <p>Haz doble clic en una línea del mapa para sacarla de servicio, o haz clic para ver su detalle y usa Sacar de servicio. El motor calcula la cascada: líneas que se sobrecargan, islas que se separan, cortes automáticos de carga y apagones.</p>
      <p className="meta">Sin cortes, el sistema opera normal en este punto de operación.</p>
    </div>
  );
}

function ImpactCard(p: Props) {
  const lowest = p.islands.filter((i) => i.hz != null).sort((a, b) => (a.hz ?? 50) - (b.hz ?? 50))[0];
  const collapsed = p.islands.some((i) => i.collapsed);
  const hzValue = collapsed ? null : lowest?.hz ?? 50;
  const fault = collapsed || (hzValue != null && hzValue < 49);
  const withstands = withstandsAt(p.timeline, p.t);
  return (
    <div className="card impact">
      {withstands ? (
        <div className="withstands">
          <div className="card-head"><div className="title"><h3>El sistema resiste este corte</h3><Info tip="Resultado final del motor Sub50 para este corte: nadie queda sin suministro y no hay cortes automáticos de carga." /></div></div>
          <p>Nadie queda sin suministro y no se pierde carga.</p>
        </div>
      ) : <>
      <div className="card-head">
        <div className="title"><h3>Personas sin suministro</h3><Info tip="Personas asignadas a las subestaciones que pierden suministro, calculadas por el motor Sub50. Los cortes automáticos de carga en islas que sobreviven se reparten en el tiempo según los MW cortados; al final la cifra es la del motor." /></div>
        <div className="title"><span className="share">{pct(p.impact.share)} del país</span><Info tip={`Sobre ${int(p.totalPeople)} personas asignadas a las subestaciones del modelo.`} /></div>
      </div>
      <div className="people">{int(p.impact.people)}</div>
      </>}
      <div className="mini-figures ruled">
        <div><div className="value-row"><b>{int(p.impact.lostLoadMw)} <small>MW</small></b><Info tip="Demanda desconectada: islas apagadas y cortes automáticos de carga (EDAC). Flujo DC del motor Sub50." /></div><span>carga perdida</span></div>
        <div><div className="value-row"><b>{int(p.impact.lostGenMw)} <small>MW</small></b><Info tip="Generación en las subestaciones que quedaron sin tensión. El motor no modela desconexiones de centrales por frecuencia o tensión." /></div><span>generación perdida</span></div>
        <div>
          <div className="value-row">
            {hzValue == null ? <b className="fault">apagón</b> : <b className={fault ? "fault" : ""}>{hz(hzValue)} <small>Hz</small></b>}
            <Info tip="Frecuencia de la isla más baja, con un modelo de una masa por isla (supuestos sin calibrar). Bajo 47,5 Hz la isla se apaga." />
          </div>
          <span>{p.islands.length > 1 ? `frecuencia ${lowest?.name.toLowerCase() ?? "más baja"}` : "frecuencia"}</span>
        </div>
      </div>
      <div className="cut-row">
        <p className="meta cut-name">Corte: {p.cuts.map((id) => cutName(p.network, id)).join(", ")}</p>
        <button className="secondary-btn" onClick={() => p.restore()}>{p.cuts.length === 1 && shutdownNode(p.cuts[0]) ? "Encender subestación" : p.cuts.length > 1 ? "Reponer líneas" : "Reponer línea"}</button>
      </div>
    </div>
  );
}

function History(p: Props) {
  const events = p.timeline.events;
  const visible = events.filter((e) => e.t <= p.t + 1e-9).length;
  const current = visible - 1;
  const ref = useRef<HTMLDivElement>(null);
  // Keep the current event in view by scrolling this card only: scrollIntoView also scrolled the panel and hid the cards above.
  useEffect(() => {
    const card = ref.current, row = card?.querySelector(".event.current");
    if (!card || !row) return;
    const c = card.getBoundingClientRect(), r = row.getBoundingClientRect();
    const head = 40; // the sticky card head covers the top of the list
    if (r.bottom > c.bottom) card.scrollTop += r.bottom - c.bottom + 8;
    else if (r.top < c.top + head) card.scrollTop -= c.top + head - r.top;
  }, [current]);
  return (
    <div className="card history" ref={ref}>
      <div className="card-head pad"><div className="title"><h3>Historial de eventos</h3></div><span className="unit">{visible} de {events.length}</span></div>
      {events.slice(0, visible).map((e, i) => (
        <button key={i} className={i === current ? "event current" : "event"} onClick={() => p.seek(e.t)}>
          <span className="badge">{i + 1}</span>
          <span className="when">{secs(e.t)} s</span>
          <span className="what">{narrate(e, p.network)}</span>
        </button>
      ))}
    </div>
  );
}
