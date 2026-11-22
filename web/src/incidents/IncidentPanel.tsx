import { useEffect } from "react";
import { Info } from "../cascade/ui";
import { cardFigures, cycleRows, effectText, incidentTag, LEVELS, NOTICES, pointText, POLICIES, responseFigures, type IncidentSource } from "./incidents";
import type { Incident } from "./useIncident";
import "./incidents.css";

/**
 * The Incidentes view of mapa 3 (docs/mapa3.md section 4.2): the documented-incident catalog in the order of its file
 * (never sorted by damage), the run options, and the result: consequence card, agentic response, prevention, the
 * cycles (those with a cascade play it on the map) and the sources. Every result carries both notices.
 */
/**
 * Props: `inc` is the `useIncident` state owned by CascadeApp. `sessionPoint` is the operating point of the session on screen
 * (null without one); it decides whether a launch reuses that session or creates a new one at the incident's hour.
 */
export function IncidentPanel({ inc, sessionPoint }: { inc: Incident; sessionPoint: string | null }) {
  useEffect(() => { inc.load(); }, []);
  const { catalog, result } = inc;
  const chosen = catalog?.incidents.find((x) => x.id === inc.selected) ?? null;

  return (
    <div className="incidents">
      <div className="card">
        <div className="card-head"><h3>Incidentes documentados</h3></div>
        <p className="meta">Elige un incidente público y simula su efecto en la red de Chile: qué pasa en la red, cómo responden los agentes defensivos y qué lo habría evitado. Es un escenario, no una reconstrucción.</p>
      </div>
      <Notices />
      {inc.error && <p className="note">{inc.error}</p>}
      {!catalog && !inc.error && <p className="meta">Cargando el catálogo…</p>}

      {catalog && !result && (
        <>
          <div className="inc-list" role="radiogroup" aria-label="Incidentes">
            {catalog.incidents.map((x) => {
              const tag = incidentTag(x);
              const on = x.id === inc.selected;
              return (
                <div key={x.id} className={on ? "card inc-card on" : "card inc-card"}>
                  <button className="inc-pick" role="radio" aria-checked={on} onClick={() => inc.select(x.id)}>
                    <span className="inc-title">{x.title}</span>
                    <span className="meta">{x.date} · corre a las {pointText(x.operating_point)}{tag && <> · <em className="inc-tag">{tag}</em></>}</span>
                  </button>
                  <ul className="inc-effects">{x.effects.map((e, i) => <li key={i}>{effectText(e)}</li>)}</ul>
                  <Sources sources={x.sources} />
                </div>
              );
            })}
          </div>

          <div className="card">
            <div className="card-head"><h3>Opciones</h3></div>
            <span className="meta">Política de los agentes defensivos</span>
            <div className="seg" role="group" aria-label="Política">
              {POLICIES.map(([p, short, name]) => (
                <button key={p} className={inc.policy === p ? "on" : ""} aria-pressed={inc.policy === p} data-tip={name} onClick={() => inc.setPolicy(p)}>{short} · {name}</button>
              ))}
            </div>
            <button className="btn inc-go" disabled={!chosen || inc.busy} onClick={() => void inc.launch()}>
              {inc.busy ? "Simulando…" : "Simular incidente"}
            </button>
            <p className="meta">{chosen
              ? sessionPoint === chosen.operating_point ? "Corre en la sesión actual." : `Necesita el backend. Se creará una sesión a las ${pointText(chosen.operating_point)}${sessionPoint ? " y se saldrá de la actual" : ""}.`
              : "Elige un incidente. Necesita el backend; se creará una sesión a la hora del incidente si la actual no calza."}</p>
          </div>
        </>
      )}

      {result && <Result inc={inc} />}
    </div>
  );
}

function Result({ inc }: { inc: Incident }) {
  const r = inc.result!;
  const tag = incidentTag(r.incident);
  const cascade = new Set(r.cascades.map((c) => c.cycle));
  return (
    <>
      <div className="card">
        <div className="card-head">
          <h3>{r.incident.title}</h3>
          <button className="text-btn" onClick={inc.close}>Cerrar incidente</button>
        </div>
        <p className="meta">Incidente simulado · política {inc.policy} · {pointText(r.incident.operating_point)}{r.seed != null ? ` · semilla ${r.seed}` : ""}{tag ? ` · ${tag}` : ""}</p>
        {r.aar?.summary && <p className="inc-text">{r.aar.summary}</p>}
      </div>

      <div className="card">
        <div className="card-head"><h3>Consecuencia</h3><span className="unit">{LEVELS[r.level] ?? r.level}</span></div>
        <div className="mini-figures inc-figures">
          {cardFigures(r.card).map((f) => (
            <div key={f.label}><span className="value-row"><b>{f.value}</b><Info tip={f.tip} /></span><span>{f.label}</span></div>
          ))}
        </div>
        <p className="meta">{r.card.note} Interrupción: {r.card.outage_duration_h.value.toLocaleString("es-CL", { maximumFractionDigits: 2 })} h{r.card.outage_duration_h.is_assumption ? " (supuesto)" : " (calibrado con el 25F [44])"}.</p>
      </div>

      <div className="card">
        <div className="card-head"><h3>Respuesta de los agentes</h3><span className="unit">indicador experimental</span></div>
        <div className="mini-figures inc-figures">
          {responseFigures(r.indicators, r.minutesPerCycle).map((f) => (
            <div key={f.label}><span className="value-row"><b>{f.value}</b><Info tip={f.tip} /></span><span>{f.label}</span></div>
          ))}
        </div>
      </div>

      {!!r.aar?.prevention.length && (
        <div className="card">
          <div className="card-head"><h3>Qué lo habría evitado</h3></div>
          <ul className="inc-list-text">{r.aar.prevention.map((p, i) => <li key={i}>{p}</li>)}</ul>
        </div>
      )}

      <div className="card">
        <div className="card-head"><h3>Ciclos</h3><span className="unit">{r.minutesPerCycle.toLocaleString("es-CL")} min por ciclo</span></div>
        {!r.cascades.length && <p className="meta">Ningún ciclo tuvo una cascada en la red: el sistema absorbió el efecto.</p>}
        <ol className="inc-cycles">
          {cycleRows(r.timeline, r.cascades).map((c) => (
            <li key={c.cycle} className={inc.playing === c.cycle ? "on" : ""}>
              <div className="inc-cycle-head">
                <b>Ciclo {c.cycle}</b><span className="meta">min {c.t_min}</span>
                {cascade.has(c.cycle) && (inc.playing === c.cycle
                  ? <button className="text-btn" onClick={inc.stop}>Quitar del mapa</button>
                  : <button className="btn" onClick={() => inc.play(c.cycle)}>Ver cascada en el mapa</button>)}
              </div>
              <ul>{c.lines.map((l, i) => <li key={i}>{l}</li>)}</ul>
            </li>
          ))}
        </ol>
      </div>

      <div className="card">
        <div className="card-head"><h3>Notas y fuentes</h3></div>
        <ul className="inc-list-text">{(r.aar?.notes ?? r.incident.notes).map((n, i) => <li key={i}>{n}</li>)}</ul>
        <Sources sources={r.aar?.sources ?? r.incident.sources} />
      </div>
      <Notices />
    </>
  );
}

const Sources = ({ sources }: { sources: IncidentSource[] }) => (
  <p className="meta inc-sources">Fuentes: {sources.map((s, i) => <span key={s.url}>{i > 0 && " · "}<a href={s.url} target="_blank" rel="noreferrer noopener">{s.label}</a></span>)}</p>
);

const Notices = () => <div className="notice inc-notices"><span>{NOTICES[0]}<br />{NOTICES[1]}</span></div>;
