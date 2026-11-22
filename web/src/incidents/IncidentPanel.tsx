import { useEffect, useRef, type KeyboardEvent } from "react";
import { Info } from "../cascade/ui";
import {
  absorbed, cardFigures, cycleRows, dateText, effectText, incidentTag, LEVELS, NOTICES, outageText, plainText, pointText, POLICIES, responseFigures,
  sourceOf, type AarCycle, type AreaNames, type Figure, type IncidentSource,
} from "./incidents";
import type { Incident } from "./useIncident";
import "./incidents.css";

/**
 * The Incidentes view of mapa 3 (docs/mapa3.md section 4.2): the documented-incident catalog in the order of its file
 * (never sorted by damage) as a list of selectable cards, the run options fixed at the bottom of the panel, and the
 * result: consequence card, agentic response, prevention, the cycles (those with a cascade play it on the map; the first
 * one plays by itself) and the sources. Every result carries both notices.
 */
/**
 * Props: `inc` is the `useIncident` state owned by CascadeApp. `sessionPoint` is the operating point of the session on screen
 * (null without one); it decides whether a launch reuses that session or creates a new one at the incident's hour.
 */
export function IncidentPanel({ inc, sessionPoint }: { inc: Incident; sessionPoint: string | null }) {
  useEffect(() => { inc.load(); }, []);
  const { catalog, result } = inc;

  return (
    <div className="incidents">
      <p className="sr-status" role="status">{inc.busy ? "Simulando el incidente…" : result ? `Simulación terminada: ${result.incident.title}` : ""}</p>
      {!result && <p className="meta">Elige un incidente público y simula su efecto en la red de Chile: qué pasa en la red, cómo responden los agentes defensivos y qué lo habría evitado. Es un escenario, no una reconstrucción.</p>}
      <Notices />
      {inc.error && (
        <div className="note inc-error" role="alert">
          <span>{inc.error}</span>
          {!catalog && <button className="secondary-btn" onClick={inc.load}>Reintentar</button>}
        </div>
      )}
      {!catalog && !inc.error && <p className="meta">Cargando el catálogo…</p>}
      {catalog && !result && <Catalog inc={inc} sessionPoint={sessionPoint} />}
      {result && <Result inc={inc} />}
    </div>
  );
}

function Catalog({ inc, sessionPoint }: { inc: Incident; sessionPoint: string | null }) {
  const list = inc.catalog!.incidents;
  const chosen = list.find((x) => x.id === inc.selected) ?? null;
  const group = useRef<HTMLDivElement>(null);
  const focusable = inc.selected ?? list[0]?.id;
  // Radio group keys: arrows move the selection and the focus, as in a native radio group.
  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === "ArrowDown" || e.key === "ArrowRight" ? 1 : e.key === "ArrowUp" || e.key === "ArrowLeft" ? -1 : 0;
    if (!step || inc.busy || !list.length) return;
    e.preventDefault();
    const at = list.findIndex((x) => x.id === inc.selected);
    const next = list[(at + step + list.length) % list.length];
    inc.select(next.id);
    group.current?.querySelector<HTMLButtonElement>(`[data-id="${next.id}"]`)?.focus();
  };
  return (
    <>
      <div className="inc-list" role="radiogroup" aria-label="Incidentes" ref={group} onKeyDown={onKey}>
        {list.map((x) => {
          const tag = incidentTag(x);
          const on = x.id === inc.selected;
          return (
            <div key={x.id} className={on ? "card inc-card on" : "card inc-card"}>
              <button className="inc-pick" role="radio" aria-checked={on} data-id={x.id} tabIndex={x.id === focusable ? 0 : -1}
                aria-disabled={inc.busy || undefined} onClick={() => !inc.busy && inc.select(x.id)}>
                <span className="inc-mark" aria-hidden />
                <span className="inc-pick-text">
                  <span className="inc-title">{x.title}</span>
                  <span className="meta">{dateText(x.date)} · simulado a las {pointText(x.operating_point)}{tag && <> · <em className="inc-tag">{tag}</em></>}</span>
                </span>
              </button>
              {on && <>
                <ul className="inc-effects">{x.effects.map((e, i) => <li key={i}>{effectText(e, inc.areas)}</li>)}</ul>
                <Sources sources={x.sources} />
              </>}
            </div>
          );
        })}
      </div>

      <div className="inc-options">
        <span className="meta" id="inc-policy">Política de los agentes defensivos</span>
        <div className="seg" role="group" aria-labelledby="inc-policy">
          {POLICIES.map(([p, short, name]) => (
            <button key={p} className={inc.policy === p ? "on" : ""} aria-pressed={inc.policy === p} disabled={inc.busy} onClick={() => inc.setPolicy(p)}>{short} · {name}</button>
          ))}
        </div>
        {inc.busy && <span className="loading-bar" aria-hidden />}
        <div className="inc-go-row">
          <button className="primary-btn" disabled={!chosen || inc.busy} onClick={() => void inc.launch()}>{inc.busy ? "Simulando…" : "Simular incidente"}</button>
          <p className="meta">{chosen
            ? sessionPoint === chosen.operating_point ? "Se simula en la sesión actual." : `Se simula a las ${pointText(chosen.operating_point)} en una sesión nueva${sessionPoint ? " y se sale de la actual" : ""}.`
            : "Elige un incidente de la lista."}</p>
        </div>
      </div>
    </>
  );
}

function Result({ inc }: { inc: Incident }) {
  const r = inc.result!;
  const areas = inc.areas;
  const tag = incidentTag(r.incident);
  const quiet = absorbed(r.card);
  const policyName = POLICIES.find(([p]) => p === r.policy)?.[2];
  const heading = useRef<HTMLHeadingElement>(null);
  // A finished run moves the panel to its heading and the focus with it, so the result is read from the top.
  useEffect(() => {
    (heading.current?.closest(".card") ?? heading.current)?.scrollIntoView({ block: "start" });
    heading.current?.focus({ preventScroll: true });
  }, [r.runId]);
  const cascade = new Set(r.cascades.map((c) => c.cycle));
  const rows = cycleRows(r.timeline, r.cascades);
  const effectCycles = new Set(r.incident.effects.map((e) => e.cycle));
  const key = rows.filter((c) => cascade.has(c.cycle) || effectCycles.has(c.cycle));
  const rest = rows.filter((c) => !key.includes(c));
  const first = r.cascades[0]?.cycle ?? null;
  return (
    <>
      <div className="card">
        <div className="card-head">
          <h3 ref={heading} tabIndex={-1} className="inc-heading">{r.incident.title}</h3>
          <button className="text-btn" onClick={inc.close}>Cerrar incidente</button>
        </div>
        <p className="meta">Incidente simulado · política {r.policy}{policyName ? ` · ${policyName}` : ""} · a las {pointText(r.incident.operating_point)}{tag ? ` · ${tag}` : ""}</p>
        {r.aar?.summary && <p className="inc-text">{plainText(r.aar.summary, areas)}</p>}
        {first != null && (
          <div className="inc-map">
            {inc.playing != null
              ? <><span className="meta">El mapa muestra la cascada del ciclo {inc.playing}.</span><button className="secondary-btn" onClick={inc.stop}>Quitar del mapa</button></>
              : <><span className="meta">La cascada no está en el mapa.</span><button className="secondary-btn" onClick={() => inc.play(first)}>Ver cascada en el mapa</button></>}
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-head"><h3>{quiet ? "El sistema absorbió el efecto" : "Consecuencia"}</h3><span className="unit">{LEVELS[r.level] ?? r.level}</span></div>
        {quiet
          ? <p className="inc-text">Nadie quedó sin suministro y no se perdió carga en la red reducida.</p>
          : <Figures list={cardFigures(r.card)} />}
        <p className="meta">{plainText(r.card.note, areas)} Interrupción: {outageText(r.card)}.</p>
      </div>

      <div className="card">
        <div className="card-head"><h3>Respuesta de los agentes</h3><span className="unit">indicador experimental</span></div>
        <Figures list={responseFigures(r.indicators, r.minutesPerCycle)} />
      </div>

      {!!r.aar?.prevention.length && (
        <div className="card">
          <div className="card-head"><h3>{quiet ? "Qué lo haría más robusto" : "Qué lo habría evitado"}</h3></div>
          <ul className="inc-list-text">{r.aar.prevention.map((p, i) => <li key={i}>{plainText(p, areas)}</li>)}</ul>
        </div>
      )}

      <div className="card">
        <div className="card-head"><h3>Ciclos</h3><span className="unit">{r.minutesPerCycle.toLocaleString("es-CL")} min por ciclo</span></div>
        {!r.cascades.length && <p className="meta">Ningún ciclo tuvo una cascada en la red: el sistema absorbió el efecto.</p>}
        <ol className="inc-cycles">{key.map((c) => <CycleRow key={c.cycle} c={c} inc={inc} cascade={cascade.has(c.cycle)} areas={areas} />)}</ol>
        {rest.length > 0 && (
          <details className="inc-more">
            <summary>Ver los {rest.length} ciclos</summary>
            <ol className="inc-cycles">{rest.map((c) => <CycleRow key={c.cycle} c={c} inc={inc} cascade={cascade.has(c.cycle)} areas={areas} />)}</ol>
          </details>
        )}
      </div>

      <div className="card">
        <div className="card-head"><h3>Notas y fuentes</h3></div>
        <ul className="inc-list-text">{(r.aar?.notes ?? r.incident.notes).map((n, i) => <li key={i}>{plainText(n, areas)}</li>)}</ul>
        <Sources sources={r.aar?.sources ?? r.incident.sources} />
      </div>
      <Notices />
    </>
  );
}

function CycleRow({ c, inc, cascade, areas }: { c: AarCycle; inc: Incident; cascade: boolean; areas: AreaNames }) {
  return (
    <li className={inc.playing === c.cycle ? "on" : ""}>
      <div className="inc-cycle-head">
        <b>Ciclo {c.cycle}</b><span className="meta">min {c.t_min}</span>
        {cascade && (inc.playing === c.cycle
          ? <button className="text-btn" onClick={inc.stop}>Quitar del mapa</button>
          : <button className="secondary-btn" onClick={() => inc.play(c.cycle)}>Ver cascada en el mapa</button>)}
      </div>
      {c.lines.length > 0 && <ul>{c.lines.map((l, i) => <li key={i}>{plainText(l, areas)}</li>)}</ul>}
    </li>
  );
}

/** Figures with their info tip; a value in words (`text`) reads as a sentence, not as a big number. */
const Figures = ({ list }: { list: Figure[] }) => (
  <div className="mini-figures inc-figures">
    {list.map((f) => (
      <div key={f.label}>
        <span className="value-row">{f.text ? <span className="inc-text-value">{f.value}</span> : <b>{f.value}</b>}<Info tip={f.tip} /></span>
        <span>{f.label}</span>
      </div>
    ))}
  </div>
);

const Sources = ({ sources }: { sources: IncidentSource[] }) => (
  <p className="meta inc-sources">Fuentes: {sources.map(sourceOf).map((s, i) => <span key={s.url}>{i > 0 && " · "}<a href={s.url} target="_blank" rel="noreferrer noopener">{s.label}</a></span>)}</p>
);

const Notices = () => <div className="notice inc-notices"><span>{NOTICES[0]}<br />{NOTICES[1]}</span></div>;
