import { useEffect, useRef } from "react";
import type { Affected } from "./affected";
import type { Supply } from "./gridsApi";
import { withstandsAt, type Impact, type IslandFrequency } from "./simulation";
import { cutName, hz, index2, int, narrate, pct, placeName, secs, usdM } from "./text";
import type { EventCost, HealthReport, N1Cost, Network, Timeline } from "./types";
import { Chevron, Info } from "./ui";

interface Props {
  /** network and timeline: what is on the map and its cascade. cuts and outBuses: the lines and substations switched off.
   *  t: playhead in simulated seconds. impact: people and MW out at `t`. islands: frequency per island at `t`.
   *  totalPeople: people the network assigns to buses. Callbacks: seek the playhead, open the assumptions view, restore
   *  every change. source: the base-map or outline note added to the "Fuente" line. */
  network: Network; timeline: Timeline; cuts: string[]; outBuses: string[]; t: number; impact: Impact; islands: IslandFrequency[]; totalPeople: number;
  seek(t: number): void; openSources(): void; restore(): void; source: string;
  /** Pre-fault health of the point (`<point>/health.json`); null in an old cache or in a session. */
  health: HealthReport | null;
  /** People the generators should feed against the people they still feed (server simulation only). */
  supply: Supply | null;
  /** People without supply at `t` grouped by comuna (dark buses only). heatOn and setHeatOn: the map's heat map of
   *  those people, toggled from this tab. */
  affected: Affected; heatOn: boolean; setHeatOn(on: boolean): void;
}

/** Tab "Simulación" (Design v5, V2 and V3): people without supply, lost load, and the numbered event history. */
export function SimulationPanel(p: Props) {
  const assumptions = p.timeline.assumptions.length;
  const edited = p.cuts.length + p.outBuses.length > 0;
  return (
    <>
      {edited ? <ImpactCard {...p} /> : <EmptyCard health={p.health} />}
      {edited && <AffectedCard {...p} />}
      {edited && p.supply && <SupplyCard supply={p.supply} />}
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
      <p>Haz clic en una línea o una subestación del mapa para ver su detalle; un segundo clic, o el botón de su detalle, la saca de servicio. El motor calcula la cascada: líneas que se sobrecargan, islas que se separan, cortes automáticos de carga y apagones.</p>
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
      <span className="load-bar"><span style={{ width: `${Math.min(1, p.impact.share) * 100}%`, background: "var(--fault)" }} /></span>
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
        <button className="secondary-btn" onClick={() => p.restore()}>{p.outBuses.length === 0 ? (p.cuts.length > 1 ? "Volver a conectar todas" : "Volver a conectar") : p.cuts.length + p.outBuses.length > 1 ? "Reponer todo" : "Volver a encender"}</button>
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

const ZONE_NAME: Record<string, string> = { NG: "Norte Grande", NC: "Norte Chico", CE: "Centro", CS: "Centro-sur", SU: "Sur" };
const SUPPLY_TIP = "Por zona: personas que sus subestaciones generadoras deberían alimentar antes de la falla y las que siguen alimentando cuando la cascada se asienta, con el porcentaje (POST /grids/simulate, reparto por flujo DC; supuesto del modelo). Sobre 100 % significa que esa zona toma gente que antes alimentaban otras. Se muestra por zona, nunca como ranking de subestaciones (docs/cyber.md 8.2).";

/** Supply per zone after the cascade: who the generators should feed against who they still feed. */
function SupplyCard({ supply }: { supply: Supply }) {
  const zones = Object.entries(supply.by_zone);
  if (!zones.length) return null;
  return (
    <div className="card state-list">
      <div className="card-head"><div className="title"><h3>Abastecimiento por zona</h3></div><Info tip={SUPPLY_TIP} /></div>
      <div className="list-head"><span>Zona · debería → alimenta</span><span>%</span></div>
      {zones.map(([z, v]) => (
        <div className="state-row" key={z}>
          <span className="ellipsis">{ZONE_NAME[z] ?? z} · {int(v.should_feed)} → {int(v.feeds)}</span>
          <span className={v.pct_fed < 100 ? "num fault" : "num"}>{v.pct_fed.toFixed(2)} %</span>
        </div>
      ))}
    </div>
  );
}

const AFFECTED_TIP = "Personas asignadas a las subestaciones sin suministro en este segundo, agrupadas por comuna (INE Censo 2024). La asignación de comunas a subestaciones es un supuesto geográfico: \"estimado\" marca una comuna que queda sin suministro solo en parte, y esa parte depende del reparto.";

/** People without supply at `t` by comuna, with the toggle of their heat map on the map. */
function AffectedCard(p: Props) {
  const others = p.impact.people - p.affected.people;
  return (
    <div className="card state-list affected">
      <div className="card-head"><div className="title"><h3>Comunas sin suministro</h3></div><Info tip={AFFECTED_TIP} /></div>
      <label className="check"><input type="checkbox" checked={p.heatOn} onChange={(e) => p.setHeatOn(e.target.checked)} />Mapa de calor de personas sin suministro</label>
      {p.affected.rows.length === 0 ? <p className="meta">Ninguna comuna sin suministro en este segundo.</p> : <>
        <div className="list-head"><span>Comuna</span><span>personas</span></div>
        <div className="rows">
          {p.affected.rows.map((r) => (
            <div className="state-row" key={r.key}>
              <span className="ellipsis">{r.name}{r.is_assumption && <small> estimado</small>}</span>
              <span className="load-bar"><span style={{ width: `${Math.min(1, r.people / r.total) * 100}%`, background: "var(--fault)" }} /></span>
              <span className="num">{int(r.people)}</span>
            </div>
          ))}
        </div>
      </>}
      {others >= 1 && <p className="meta">Otras {int(others)} personas sin suministro por cortes automáticos de carga (EDAC), que el modelo no asigna a una comuna.</p>}
      <p className="source">Fuente: INE Censo 2024. Asignación de comunas a subestaciones: supuesto.</p>
    </div>
  );
}
