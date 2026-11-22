import { useEffect, useRef, useState } from "react";
import type { Pick } from "./clicks";
import type { Supply } from "./gridsApi";
import type { Disaster } from "./Scenarios";
import { systemFrequency, voltageCollapse, withstandsAt, type Impact, type IslandFrequency } from "./simulation";
import { cutName, hoursText, hz, index2, int, narrate, pct, pct2, placeName, secs, usdM } from "./text";
import type { Assumed, EventCost, HealthReport, N1Cost, Network, Timeline } from "./types";
import { Chevron, CopyLink, Info } from "./ui";

interface Props {
  /** network and timeline: what is on the map and its cascade. cuts and outBuses: the lines and substations switched off.
   *  t: playhead in simulated seconds. impact: people and MW out at `t`. islands: frequency per island at `t`.
   *  darkCount: substations without supply at `t`. totalPeople: people the network assigns to buses. Callbacks: seek the
   *  playhead, open the assumptions view, restore every change. source: the base-map or outline note added to the "Fuente" line. */
  network: Network; timeline: Timeline; cuts: string[]; outBuses: string[]; t: number; impact: Impact; islands: IslandFrequency[]; darkCount: number; totalPeople: number;
  seek(t: number): void; openSources(): void; restore(): void; source: string;
  /** Pre-fault health of the point (`<point>/health.json`); null in an old cache or in a session. */
  health: HealthReport | null;
  /** People the generators should feed against the people they still feed (server simulation only). */
  supply: Supply | null;
  /** The Desastres entry on the map, for the real figure next to the model's (F-06); null for the user's own changes. */
  disaster: Disaster | null;
  /** The URL describes the view, so "Copiar enlace" is offered (never in a session). */
  shareable: boolean;
  /** Cold start card: select a line or substation from the search field, open the 25F. */
  select(pick: Pick): void;
  /** Something to simulate: cuts, substations off or scenario changes (the assistant's). */
  edited: boolean;
  /** An incident or cyber cascade on the map: whose it is, the way back to its run and how to take it off the map. */
  external?: ExternalCascade | null;
}

export interface ExternalCascade { label: string; back: string; open(): void; remove(): void }

/** Tab "Simulación" (Design v5, V2 and V3): people without supply, lost load, and the numbered event history. */
export function SimulationPanel(p: Props) {
  const assumptions = p.timeline.assumptions.length;
  const edited = p.edited || !!p.external; // the assistant's changes count, not only cuts
  return (
    <>
      {edited && <ImpactCard {...p} />}
      {/* The history sits right under the impact card, so its current row stays in view while the cascade plays. */}
      {edited && <History {...p} />}
      {edited && p.supply && <SupplyCard supply={p.supply} />}
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
/** The regulatory valuation, with the hours that cost really uses (G-07: they are calibrated for a blackout, assumed otherwise). */
const costTip = (hours: Assumed | undefined) =>
  `Valoración regulatoria (costo de falla CNE, 8,79 US$/kWh) de la energía no servida, con ${hours ? hoursText(hours) : "una duración supuesta"} de corte. No es la pérdida económica medida y no entra en el índice.`;

const isN1 = (c: EventCost | N1Cost | undefined): c is N1Cost => !!c && "n1_expected_cost_usd" in c;
const bindingLabel = (r: HealthReport) => r.margins.find((m) => m.key === r.binding)?.label.toLowerCase() ?? r.binding ?? "";

function IndexFigure({ report, tip, label }: { report: HealthReport; tip: string; label: string }) {
  return (
    <div>
      <div className="value-row"><b>{index2(report.index)}{report.uncertain && <small> incierto</small>}</b><Info tip={`${INDEX_TIP} ${tip} Limita: ${bindingLabel(report)}.`} /></div>
      <span>{label}</span>
    </div>
  );
}

/** Pre-fault index and N-1 money at risk, behind the closed "Indicadores técnicos" disclosure; nothing when health.json is missing. */
export function PrefaultHealth({ health }: { health: HealthReport }) {
  const cost = isN1(health.cost) ? health.cost : null;
  const hours = cost?.outage_duration_h;
  return (
    <details className="disclosure-block">
      <summary><Chevron dir="right" color="currentColor" /><span>Indicadores técnicos</span></summary>
      <div className="mini-figures">
        <IndexFigure report={health} label="Margen de la red" tip="Antes de cualquier corte; no se compara con el índice después de un corte." />
        {cost && <>
          <div>
            <div className="value-row"><b>{usdM(cost.n1_expected_cost_usd)}</b><Info tip={`${costTip(hours)} Promedio de los ${cost.n1_cuts} cortes simples de una línea, cada uno con el mismo peso (supuesto): ${cost.n1_cuts_with_cost} tienen costo${cost.n1_cost_share.share_band ? ` y los ${cost.n1_cost_share.count} más caros suman ${cost.n1_cost_share.share_band} del total` : ""}.`} /></div>
            <span>Costo esperado si falla una línea cualquiera</span>
          </div>
          <div>
            <div className="value-row"><b>{usdM(cost.n1_worst_cost_usd)}</b><Info tip={`${costTip(hours)} Peor corte simple de una línea. Puede ser un artefacto de la red resumida: cortar una línea resumida corta todo el corredor.`} /></div>
            <span>Costo si falla la peor línea</span>
          </div>
        </>}
      </div>
      <p className="meta">{cost ? `Modelo Sub50 antes de cualquier corte, con ${hoursText(cost.outage_duration_h)} de corte.` : "Modelo Sub50 antes de cualquier corte."}</p>
    </details>
  );
}

/** After-cut index and event cost, read at the end of the simulation (D5); each part hides when an old cache lacks it. */
export function EndOfRun({ timeline }: { timeline: Timeline }) {
  const report = timeline.health;
  const fromReport = report && !isN1(report.cost) ? report.cost : undefined;
  const usd = fromReport?.cost_usd ?? timeline.summary.failure_cost_usd;
  if (!report && usd == null) return null;
  const rule = !!fromReport?.voltage_rule;
  const hours = fromReport?.outage_duration_h ?? timeline.summary.outage_duration_h;
  const ruleTip = rule ? " Incluye las islas apagadas por la regla de colapso de tensión del 25F: está documentado, no calculado." : "";
  return (
    <div className="end-of-run">
      <h4 className="subhead">Al final de la simulación</h4>
      <div className="mini-figures">
        {report && <IndexFigure report={report} label="índice de margen operativo" tip="Al final de la simulación, después del corte; no se compara con el índice antes del corte." />}
        {usd != null && (
          <div>
            <div className="value-row"><b>{usdM(usd)}</b><Info tip={`${costTip(hours)}${ruleTip}`} /></div>
            <span>{rule ? "costo estimado, colapso por regla" : "costo estimado"}</span>
          </div>
        )}
      </div>
      <p className="meta">Índice de margen operativo (modelo) y valoración regulatoria (costo de falla CNE){hours ? `, con ${hoursText(hours)} de corte` : ""}.</p>
    </div>
  );
}

function ImpactCard(p: Props) {
  const freq = systemFrequency(p.islands, p.darkCount, p.network.nodes.length);
  const voltage = voltageCollapse(p.timeline);
  const withstands = withstandsAt(p.timeline, p.t);
  const copy = p.shareable ? <CopyLink /> : null;
  return (
    <div className="card impact">
      {withstands ? (
        <div className="withstands">
          <div className="card-head"><div className="title"><h3>El sistema resiste este corte</h3><Info tip="Resultado final del motor Sub50 para este corte: nadie queda sin suministro y no hay cortes automáticos de carga." /></div>{copy}</div>
          <p>Nadie queda sin suministro y no se pierde carga.</p>
        </div>
      ) : <>
      <div className="card-head">
        <div className="title"><h3>Personas sin suministro</h3><Info tip="Personas asignadas a las subestaciones que pierden suministro, calculadas por el motor Sub50. Los cortes automáticos de carga en islas que sobreviven se reparten en el tiempo según los MW cortados; al final la cifra es la del motor." /></div>
        <div className="title"><span className="share">{pct(p.impact.share)} del país</span><Info tip={`Sobre ${int(p.totalPeople)} personas asignadas a las subestaciones del modelo.`} />{copy}</div>
      </div>
      <div className="people">{int(p.impact.people)}</div>
      {p.disaster?.real && <div className="value-row real-row"><span>{p.disaster.real.text}</span><Info tip={p.disaster.real.tip} /></div>}
      </>}
      <div className="mini-figures ruled">
        <div><div className="value-row"><b>{int(p.impact.lostLoadMw)} <small>MW</small></b><Info tip="Demanda desconectada: islas apagadas y cortes automáticos de carga (EDAC), según el motor Sub50." /></div><span>carga perdida</span></div>
        <div><div className="value-row"><b>{int(p.impact.lostGenMw)} <small>MW</small></b><Info tip="Generación en las subestaciones que quedaron sin tensión. El motor no modela desconexiones de centrales por frecuencia o tensión." /></div><span>generación perdida</span></div>
        <div>
          <div className="value-row">
            {freq.blackout ? <b className="fault">apagón</b> : <b className={freq.fault ? "fault" : ""}>{hz(freq.hz)} <small>Hz</small></b>}
            <Info tip={freq.blackout
              ? `Todas las subestaciones quedaron sin suministro: no hay frecuencia que medir.${voltage ? " Las islas se apagaron por la regla de colapso de tensión del modelo (la del 25F), no porque la frecuencia cayera." : ""}`
              : "Frecuencia de la isla viva más baja, con un modelo de una masa por isla (supuestos sin calibrar). Bajo 47,5 Hz la isla se apaga."} />
          </div>
          <span>{freq.blackout ? (voltage ? "colapso por tensión (regla del modelo)" : "frecuencia") : freq.island && p.islands.length > 1 ? `frecuencia ${freq.island.name.toLowerCase()}` : "frecuencia"}</span>
        </div>
      </div>
      {p.timeline.truncated && (
        <p className="notice truncated" role="note">{`La cascada se cortó en ${p.timeline.summary.stages} etapas (límite del motor); podría seguir.`}</p>
      )}
      <EndOfRun timeline={p.timeline} />
      {p.external ? (
        <div className="cut-row external">
          <p className="meta cut-name">{p.external.label}</p>
          <span className="row-btns"><button className="secondary-btn" onClick={p.external.open}>{p.external.back}</button><button className="text-btn" onClick={p.external.remove}>Quitar del mapa</button></span>
        </div>
      ) : <div className="cut-row">
        <p className="meta cut-name">{[p.cuts.length > 0 && `Corte: ${p.cuts.map((id) => cutName(p.network, id)).join(", ")}`, p.outBuses.length > 0 && `Subestaciones fuera de servicio: ${p.outBuses.map((id) => placeName(p.network.nodes.find((n) => n.id === id)?.name ?? id)).join(", ")}`].filter(Boolean).join(". ")}</p>
        <button className="secondary-btn" onClick={() => p.restore()}>{p.outBuses.length === 0 ? (p.cuts.length > 1 ? "Volver a conectar todas" : "Volver a conectar") : p.cuts.length + p.outBuses.length > 1 ? "Reponer todo" : "Volver a encender"}</button>
      </div>}
    </div>
  );
}

/**
 * Numbered event history. A click on a row seeks to its second and keeps that row as the current one while the time does
 * not change, also when several events share the second (A2-05). The current row is kept in view in this card and, when
 * the card itself runs below the panel, in the panel too (A2-04).
 */
function History(p: Props) {
  const events = p.timeline.events;
  const visible = events.filter((e) => e.t <= p.t + 1e-9).length;
  const [chosen, setChosen] = useState<{ i: number; t: number } | null>(null);
  const current = chosen && Math.abs(chosen.t - p.t) < 1e-9 && chosen.i < visible ? chosen.i : visible - 1;
  const ref = useRef<HTMLDivElement>(null);
  // Scroll this card first: scrollIntoView also scrolled the panel and hid the cards above.
  useEffect(() => {
    const card = ref.current, row = card?.querySelector(".event.current");
    if (!card || !row) return;
    const c = card.getBoundingClientRect(), r = row.getBoundingClientRect();
    // The sticky head and its 4 px mask cover the top of the list: rows count as visible below that edge.
    const headEl = card.querySelector<HTMLElement>(".card-head");
    const edge = () => (headEl?.getBoundingClientRect().bottom ?? c.top + 40) + 4;
    if (r.bottom > c.bottom) card.scrollTop += r.bottom - c.bottom + 8;
    else if (r.top < edge()) card.scrollTop -= edge() - r.top;
    // A row cut in half under the sticky head reads as a stray line (G-25): scroll it fully under the head. The current
    // row moves up by as much, so it stays in view.
    hideHalfRow(card);
    // The card can itself end below the panel: then move the panel just enough for the row to be whole.
    const body = card.closest(".panel-body");
    if (!body) return;
    const b = body.getBoundingClientRect(), r2 = row.getBoundingClientRect();
    if (r2.bottom > b.bottom - 12) body.scrollTop += r2.bottom - b.bottom + 12;
  }, [current]);
  // The card changes height as the cards above it grow at the end of the run: check the half row again then.
  useEffect(() => {
    const card = ref.current;
    if (!card || typeof ResizeObserver === "undefined") return;
    const watch = new ResizeObserver(() => hideHalfRow(card));
    watch.observe(card);
    return () => watch.disconnect();
  }, []);
  return (
    <div className={visible > 3 ? "card history tall" : "card history"} ref={ref}>
      <div className="card-head pad"><div className="title"><h3>Historial de eventos</h3></div><span className="unit">{visible} de {events.length}</span></div>
      {events.slice(0, visible).map((e, i) => (
        <button key={i} className={i === current ? "event current" : "event"} aria-current={i === current || undefined} onClick={() => { setChosen({ i, t: e.t }); p.seek(e.t); }}>
          <span className="badge">{i + 1}</span>
          <span className="when">{secs(e.t)} s</span>
          <span className="what">{narrate(e, p.network)}</span>
        </button>
      ))}
    </div>
  );
}

/**
 * A row cut in half under the sticky head reads as a stray line (G-25): scroll it fully under the head (the head's real
 * edge plus its 4 px mask). The rows below move up by as much, so the current row stays in view.
 */
function hideHalfRow(card: HTMLElement) {
  card.style.paddingBottom = "";
  const top = (card.querySelector(".card-head")?.getBoundingClientRect().bottom ?? card.getBoundingClientRect().top + 40) + 4;
  const rows = [...card.querySelectorAll<HTMLElement>(".event")];
  const cut = rows.find((e) => e.getBoundingClientRect().bottom > top + 1);
  if (!cut || cut.classList.contains("current")) return;
  const r = cut.getBoundingClientRect();
  if (r.top >= top - 1) return;
  // At the end of the list there may be no room left to scroll: a little bottom padding makes it (at most one row).
  const room = card.scrollHeight - card.clientHeight - card.scrollTop;
  const need = r.bottom - top;
  if (need > room) card.style.paddingBottom = `${8 + need - room}px`;
  card.scrollTop += need;
}

const ZONE_NAME: Record<string, string> = { NG: "Norte Grande", NC: "Norte Chico", CE: "Centro", CS: "Centro-sur", SU: "Sur" };
const SUPPLY_TIP = "Por zona: personas que sus subestaciones generadoras deberían alimentar antes de la falla y las que siguen alimentando cuando la cascada se asienta, con el porcentaje, repartidas según el flujo de potencia del modelo (supuesto del modelo). Sobre 100 % significa que esa zona toma gente que antes alimentaban otras. Se muestra por zona, nunca como un ranking de subestaciones.";

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
          <span className={v.pct_fed < 100 ? "num fault" : "num"}>{pct2(v.pct_fed)}</span>
        </div>
      ))}
    </div>
  );
}
