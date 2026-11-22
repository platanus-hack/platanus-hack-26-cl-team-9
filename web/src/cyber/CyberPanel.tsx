import { useEffect, useRef, useState } from "react";
import { pct } from "../cascade/text";
import { Info } from "../cascade/ui";
import { visible } from "../incidents/incidents";
import { areaOrder, DEFENSES, defenseName, eventText, formFields, frameFigures, NOTICE, OUTCOME_LABEL, STATE_LABEL, unitText, type AreaState, type CyberCatalog, type Outcome } from "./cyber";
import type { Cyber } from "./useCyber";
import "./cyber.css";

const LLM_OFF = "No disponible: el servidor no tiene un modelo de lenguaje configurado.";

/** What the scenario is, with the threshold that closes it as a share of the demand left without supply. */
function about(threshold: number) {
  return `Una intrusión hipotética aparece en un área operativa al azar y salta a las áreas vecinas. Un área comprometida, al rato, pierde el despacho remoto y parte de su generación, y la red responde con la cascada que calcula el motor. La defensa segmenta y repara con cuadrillas limitadas. El escenario termina cuando queda sin suministro el ${pct(threshold)} de la demanda, o cuando no queda intrusión y todo lo afectado se reparó.`;
}
const threshold = (cat: CyberCatalog | null, params?: Record<string, number>) => params?.attack_win_lost_share ?? cat?.defaults.attack_win_lost_share ?? 0.8;

/**
 * The Ciberataque view: a hypothetical intrusion that jumps between neighbouring operating areas while a defence with
 * limited field crews segments and repairs them. The form comes from `GET /sim/catalog` → `cyber_attack`: the defence and
 * the action first, the ten assumed parameters behind a closed disclosure. The run, the outcome and every number come
 * from the backend. Area level only, never a substation or line (docs/cyber.md 8).
 */
export function CyberPanel({ c }: { c: Cyber }) {
  useEffect(() => { c.load(); }, []);
  const { catalog, run } = c;
  const text = about(threshold(catalog, run?.params));
  return (
    <div className="cyber">
      {run
        ? <details className="cy-about"><summary>Cómo funciona el escenario</summary><p className="meta">{text}</p></details>
        : <p className="meta">{text}</p>}
      <div className="notice"><span>{NOTICE}</span></div>
      {c.error && (
        <div className="note cy-error" role="alert">
          <span>{c.error}</span>
          {!catalog && <button className="secondary-btn" onClick={c.load}>Reintentar</button>}
        </div>
      )}
      {!catalog && !c.error && <p className="meta">Cargando el escenario…</p>}
      {catalog && !run && <Form c={c} />}
      {run && <Result c={c} />}
    </div>
  );
}

function Form({ c }: { c: Cyber }) {
  const cat = c.catalog!;
  const [open, setOpen] = useState(false);
  const invalid = Object.keys(c.errors).length;
  useEffect(() => { if (invalid) setOpen(true); }, [invalid]); // a blocked launch shows the fields to fix
  return (
    <div className="card">
      <span className="meta" id="cy-defense">Defensa</span>
      <div className="seg cy-defense" role="group" aria-labelledby="cy-defense">
        {DEFENSES.map(([d, name]) => {
          const off = d === "llm" && !c.llmAvailable;
          return (
            <button key={d} className={c.defense === d ? "on" : ""} aria-pressed={c.defense === d} disabled={off || c.busy}
              data-tip={off ? LLM_OFF : undefined} onClick={() => c.setDefense(d)}>{name}</button>
          );
        })}
      </div>
      <p className="meta">{c.defense === "llm"
        ? "El comandante IA usa el modelo del servidor y solo elige entre acciones ya validadas; si no responde, sigue la política C."
        : `Política por reglas sobre los recursos disponibles.${c.llmAvailable ? "" : ` Comandante IA: ${LLM_OFF.toLowerCase()}`}`}</p>
      {invalid > 0 && <p className="note" role="alert">Revisa {invalid === 1 ? "el parámetro marcado" : `los ${invalid} parámetros marcados`} antes de simular.</p>}
      <div className="cy-go-row">
        <button className="primary-btn" disabled={c.busy || invalid > 0} onClick={() => void c.launch()}>{c.busy ? "Simulando…" : "Simular escenario"}</button>
        <p className="meta">Se simula en la red base a las 13:00 del 1 nov 2026, en una sesión nueva.</p>
      </div>
      <details className="cy-params" open={open} onToggle={(e) => setOpen(e.currentTarget.open)}>
        <summary>Parámetros (supuestos)</summary>
        <p className="meta">Valores del escenario, no medidos. Un ciclo dura 5 minutos.</p>
        <div className="cy-fields">
          {formFields(cat).map((f) => {
            const id = `cy-${f.key}`;
            const err = c.errors[f.key];
            return (
              <div key={f.key} className={err ? "cy-field bad" : "cy-field"}>
                <label htmlFor={id}>{f.label}</label>
                <span className="cy-input">
                  <input id={id} type="text" inputMode={f.unit === "prob" || f.unit === "share" ? "decimal" : "numeric"} autoComplete="off"
                    value={c.texts[f.key] ?? ""} aria-invalid={!!err || undefined} aria-describedby={err ? `${id}-err` : undefined}
                    onChange={(e) => c.setText(f.key, e.target.value)} onBlur={() => c.check(f.key)} />
                  <span className="unit">{unitText(f.unit)}</span>
                </span>
                {err && <span className="cy-field-error" id={`${id}-err`}>{err}</span>}
              </div>
            );
          })}
        </div>
        <button className="secondary-btn" onClick={c.resetParams}>Restablecer parámetros</button>
      </details>
    </div>
  );
}

function Result({ c }: { c: Cyber }) {
  const run = c.run!;
  const areas = c.catalog?.areas ?? [];
  const name = (id: string) => areas.find((a) => a.id === id)?.name ?? id;
  const f = run.frames[c.at];
  const last = run.frames[run.frames.length - 1];
  const outcome: Outcome | null = run.report?.outcome ?? (run.done ? last?.outcome ?? null : null);
  const share = threshold(c.catalog, run.params);
  const first = run.frames.find((x) => x.transient && visible(x.transient))?.cycle ?? null;
  const heading = useRef<HTMLHeadingElement>(null);
  // The outcome takes the focus when the run ends, so it is read first.
  useEffect(() => { if (run.done) heading.current?.focus({ preventScroll: true }); }, [run.done]);
  const done = last?.cycle ?? 0;
  return (
    <>
      <div className="card cy-outcome">
        <div className="card-head">
          <h3 ref={heading} tabIndex={-1} className="cy-heading">{outcome ? OUTCOME_LABEL[outcome] : c.busy ? `Ciclo ${done} de ${run.horizon} · simulando` : "Sin resultado"}</h3>
          <button className="text-btn" onClick={c.close}>Cerrar escenario</button>
        </div>
        {c.busy && <div className="cy-progress" role="progressbar" aria-label="Avance de la simulación" aria-valuemin={0} aria-valuemax={run.horizon} aria-valuenow={done}><span style={{ width: `${Math.min(100, (done / run.horizon) * 100)}%` }} /></div>}
        {outcome && <p className="cy-text">{outcomeText(outcome, share, run.horizon)}</p>}
        <p className="meta">Defensa {defenseName(run.defense)}{run.report?.start_area ? ` · inicio en ${name(run.report.start_area)}` : ""}{run.report ? ` · hasta ${run.report.peak_active_areas} ${run.report.peak_active_areas === 1 ? "área" : "áreas"} con intrusión a la vez` : ""}</p>
        {run.done && first != null && (
          <div className="cy-map">
            {c.mapCycle != null
              ? <><span className="meta">El mapa muestra la cascada del ciclo {c.mapCycle}.</span><button className="secondary-btn" onClick={() => c.showOnMap(null)}>Quitar del mapa</button></>
              : <><span className="meta">La cascada no está en el mapa.</span><button className="secondary-btn" onClick={() => c.showOnMap(first)}>Ver cascada en el mapa</button></>}
          </div>
        )}
      </div>

      {f && (
        <div className="card">
          <div className="card-head"><h3>Ciclo {f.cycle}</h3><span className="unit">min {f.t_min}</span></div>
          <div className="cy-controls">
            {c.playing ? <button className="secondary-btn" onClick={c.pause}>Pausa</button> : <button className="secondary-btn" onClick={c.play} disabled={c.busy}>Reproducir</button>}
            <input type="range" className="cy-range" min={0} max={run.frames.length - 1} value={c.at} onChange={(e) => c.seek(Number(e.target.value))} aria-label="Ciclo" />
            {f.transient && visible(f.transient) && (c.mapCycle === f.cycle
              ? <button className="text-btn" onClick={() => c.showOnMap(null)}>Quitar del mapa</button>
              : <button className="secondary-btn" onClick={() => c.showOnMap(f.cycle)}>Ver en el mapa</button>)}
          </div>
          <div className="mini-figures cy-figures">
            {frameFigures(f).map((x) => <div key={x.label}><span className="value-row"><b>{x.value}</b><Info tip={x.tip} /></span><span>{x.label}</span></div>)}
          </div>
          <p className="meta">Cuadrillas ocupadas: {f.crews_busy.toLocaleString("es-CL")} de {run.crews.toLocaleString("es-CL")}.</p>
          <div className="cy-areas" role="list" aria-label="Áreas operativas">
            {areaOrder(areas, f.areas).map((a) => {
              const st: AreaState = f.areas[a.id] ?? "clean";
              return (
                <div key={a.id} role="listitem" className={`cy-area ${st}`} title={`${a.name}: ${STATE_LABEL[st]}`}>
                  <span className="cy-area-name">{a.name}</span>
                  <span className="cy-area-meta">{STATE_LABEL[st]} · {a.id}</span>
                </div>
              );
            })}
          </div>
          {!!f.events.length && <ul className="cy-events">{f.events.map((e, i) => <li key={i}>{eventText(e, name)}</li>)}</ul>}
        </div>
      )}

      <div className="card">
        <div className="card-head"><h3>Leyenda</h3></div>
        <div className="cy-legend">{(["struck", "compromised", "eradicated", "clean"] as AreaState[]).map((s) => <span key={s} className={`cy-area ${s}`}><span className="cy-area-meta">{STATE_LABEL[s]}</span></span>)}</div>
        <p className="meta">Valores del modelo para un escenario hipotético, no una predicción. La defensa ve solo lo que muestra la supervisión.</p>
      </div>
    </>
  );
}

function outcomeText(o: Outcome, share: number, horizon: number): string {
  if (o === "attack") return `Quedó sin suministro al menos el ${pct(share)} de la demanda, el umbral que cierra el escenario.`;
  if (o === "defense") return "No quedó ninguna área con intrusión y todas las afectadas se repararon.";
  return `Al terminar los ${horizon} ciclos seguía habiendo intrusión, sin llegar al ${pct(share)} de la demanda sin suministro.`;
}
