import { useEffect, useRef } from "react";
import { withstandsAt, type Impact, type IslandFrequency } from "./simulation";
import { cutName, hz, index2, int, narrate, pct, placeName, secs, usdM } from "./text";
import type { EventCost, HealthReport, N1Cost, Network, Timeline } from "./types";
import { Chevron, Info } from "./ui";

interface Props {
  network: Network; timeline: Timeline; cuts: string[]; outBuses: string[]; t: number; impact: Impact; islands: IslandFrequency[]; totalPeople: number;
  seek(t: number): void; openSources(): void; restore(): void; source: string;
  /** Pre-fault health of the point (`<point>/health.json`); null in an old cache or in a session. */
  health: HealthReport | null;
}

/** Tab "Simulación" (Design v5, V2 and V3): people without supply, lost load, and the numbered event history. */
export function SimulationPanel(p: Props) {
  const assumptions = p.timeline.assumptions.length;
  const edited = p.cuts.length + p.outBuses.length > 0;
  return (
    <>
      {edited ? <ImpactCard {...p} /> : <EmptyCard health={p.health} />}
      {edited && <History {...p} />}
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

const INDEX_TIP = "Índice de margen operativo (modelo): índice propio de Sub50, no un indicador del CEN ni de la SEC. Es el mínimo de los márgenes al límite (1 holgado, 0 en el límite): el eslabón más débil manda.";
const COST_TIP = "Valoración regulatoria (costo de falla CNE, 8,79 US$/kWh) de la energía no servida, con 4 h de corte supuestas. No es la pérdida económica medida y no entra en el índice.";
const COST_CAPTION = "Índice de margen operativo (modelo) y valoración regulatoria (costo de falla CNE), 4 h supuestas.";

const isN1 = (c: EventCost | N1Cost | undefined): c is N1Cost => !!c && "n1_expected_cost_usd" in c;
const bindingLabel = (r: HealthReport) => r.margins.find((m) => m.key === r.binding)?.label.toLowerCase() ?? r.binding ?? "";

function IndexFigure({ report, tip }: { report: HealthReport; tip: string }) {
  return (
    <div>
      <div className="value-row"><b>{index2(report.index)}{report.uncertain && <small> incierto</small>}</b><Info tip={`${INDEX_TIP} ${tip} Limita: ${bindingLabel(report)}.`} /></div>
      <span>índice de margen operativo</span>
    </div>
  );
}

/** Pre-fault index and N-1 money at risk, side by side; nothing when health.json is missing. */
function PrefaultHealth({ health }: { health: HealthReport }) {
  const cost = isN1(health.cost) ? health.cost : null;
  const hours = cost ? `${cost.outage_duration_h.value} h` : "4 h";
  return (
    <>
      <div className="mini-figures ruled">
        <IndexFigure report={health} tip="Antes de cualquier corte; no se compara con el índice después de un corte." />
        {cost && <>
          <div>
            <div className="value-row"><b>{usdM(cost.n1_expected_cost_usd)}</b><Info tip={`${COST_TIP} Promedio de los ${cost.n1_cuts} cortes simples de una línea, cada uno con el mismo peso (supuesto): ${cost.n1_cuts_with_cost} tienen costo${cost.n1_cost_share.share_band ? ` y los ${cost.n1_cost_share.count} más caros suman ${cost.n1_cost_share.share_band} del total` : ""}.`} /></div>
            <span>en riesgo N-1, esperado</span>
          </div>
          <div>
            <div className="value-row"><b>{usdM(cost.n1_worst_cost_usd)}</b><Info tip={`${COST_TIP} Peor corte simple, ${hours} supuestas. Puede ser un artefacto de la red reducida: cortar una línea reducida corta todo el corredor.`} /></div>
            <span>en riesgo N-1, peor</span>
          </div>
        </>}
      </div>
      <p className="meta">{cost ? `Dinero en riesgo N-1 (modelo). ${COST_CAPTION}` : "Índice de margen operativo (modelo)."}</p>
    </>
  );
}

function EmptyCard({ health }: { health: HealthReport | null }) {
  return (
    <div className="card empty">
      <h3>Escenario nuevo</h3>
      <p>Haz doble clic en una línea del mapa para sacarla de servicio, o haz clic para ver su detalle y usa Sacar de servicio. El motor calcula la cascada: líneas que se sobrecargan, islas que se separan, cortes automáticos de carga y apagones.</p>
      <p className="meta">Sin cortes, el sistema opera normal en este punto de operación.</p>
      {health && <PrefaultHealth health={health} />}
    </div>
  );
}

/** After-cut index and event cost at the end of the simulation; each part hides when an old cache lacks it. */
function EventHealth({ timeline }: { timeline: Timeline }) {
  const report = timeline.health;
  const fromReport = report && !isN1(report.cost) ? report.cost : undefined;
  const usd = fromReport?.cost_usd ?? timeline.summary.failure_cost_usd;
  if (!report && usd == null) return null;
  const rule = !!fromReport?.voltage_rule;
  const hours = (fromReport?.outage_duration_h ?? timeline.summary.outage_duration_h)?.value ?? 4;
  const ruleTip = rule ? " Incluye las islas apagadas por la regla de colapso de tensión del 25F: está documentado, no calculado." : "";
  return (
    <>
      <div className="mini-figures ruled">
        {report && <IndexFigure report={report} tip="Al final de la simulación, después del corte; no se compara con el índice antes del corte." />}
        {usd != null && (
          <div>
            <div className="value-row"><b>{usdM(usd)}</b><Info tip={`${COST_TIP} Duración: ${hours} h supuestas. Valor al final de la simulación.${ruleTip}`} /></div>
            <span>{rule ? "costo estimado, colapso por regla" : "costo estimado"}</span>
          </div>
        )}
      </div>
      <p className="meta">Al final de la simulación. {COST_CAPTION}</p>
    </>
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
      {p.timeline.truncated && (
        <p className="notice truncated" role="note">{`La cascada se cortó en ${p.timeline.summary.stages} etapas (límite del motor); podría seguir.`}</p>
      )}
      <EventHealth timeline={p.timeline} />
      <div className="cut-row">
        <p className="meta cut-name">{[p.cuts.length > 0 && `Corte: ${p.cuts.map((id) => cutName(p.network, id)).join(", ")}`, p.outBuses.length > 0 && `Subestaciones fuera de servicio: ${p.outBuses.map((id) => placeName(p.network.nodes.find((n) => n.id === id)?.name ?? id)).join(", ")}`].filter(Boolean).join(". ")}</p>
        <button className="secondary-btn" onClick={() => p.restore()}>{p.outBuses.length === 0 ? (p.cuts.length > 1 ? "Reponer líneas" : "Reponer línea") : p.cuts.length + p.outBuses.length > 1 ? "Reponer todo" : "Encender subestación"}</button>
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
