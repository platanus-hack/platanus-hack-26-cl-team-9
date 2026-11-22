import { useEffect } from "react";
import { DEFENSES, eventText, FIELDS, frameFigures, NOTICE, OUTCOME_LABEL, shown, STATE_LABEL, stored, type AreaState } from "./cyber";
import type { Cyber } from "./useCyber";
import "./cyber.css";

/**
 * The Ciberataque view: a hypothetical intrusion that jumps between neighbouring operating areas while a defence with
 * limited field crews segments and repairs them. The form comes from `GET /sim/catalog` → `cyber_attack`; the run, the
 * outcome and every number come from the backend. Area level only, never a substation or line (docs/cyber.md 8).
 */
export function CyberPanel({ c }: { c: Cyber }) {
  useEffect(() => { c.load(); }, []);
  const { catalog, run } = c;
  return (
    <div className="cyber">
      <div className="card">
        <div className="card-head"><h3>Ciberataque simulado</h3></div>
        <p className="meta">Una intrusión aparece en un área operativa al azar y salta a las áreas vecinas. Un área comprometida, al rato, pierde el despacho remoto y parte de su generación, y la red responde con su cascada real. La defensa segmenta y repara con cuadrillas limitadas. Gana el ataque si la red pierde el umbral de demanda; gana la defensa si no queda intrusión y todo se reparó.</p>
      </div>
      <div className="notice"><span>{NOTICE}</span></div>
      {c.error && <p className="note">{c.error}</p>}
      {!catalog && !c.error && <p className="meta">Cargando el escenario…</p>}
      {catalog && !run && <Form c={c} />}
      {run && <Result c={c} />}
    </div>
  );
}

function Form({ c }: { c: Cyber }) {
  const cat = c.catalog!;
  return (
    <div className="card">
      <div className="card-head"><h3>Parámetros</h3><span className="unit">supuestos, ciclos de 5 min</span></div>
      <div className="cy-fields">
        {FIELDS.filter((f) => f.key in cat.bounds).map((f) => {
          const [lo, hi] = cat.bounds[f.key];
          return (
            <label key={f.key} className="cy-field">
              <span>{f.label}</span>
              <span className="cy-input">
                <input type="number" min={shown(f.unit, lo)} max={shown(f.unit, hi)} step={1} value={shown(f.unit, c.params[f.key] ?? cat.defaults[f.key])}
                  onChange={(e) => c.setParam(f.key, stored(f.unit, Number(e.target.value)))} />
                <span className="unit">{f.unit === "ciclos" ? "ciclos" : "%"}</span>
              </span>
            </label>
          );
        })}
        <label className="cy-field">
          <span>Cuadrillas de terreno</span>
          <span className="cy-input"><input type="number" min={0} max={60} step={1} value={c.crews} onChange={(e) => c.setCrews(Math.max(0, Math.round(Number(e.target.value))))} /></span>
        </label>
        <label className="cy-field">
          <span>Semilla (vacía: al azar)</span>
          <span className="cy-input"><input type="number" min={0} step={1} value={c.seed ?? ""} onChange={(e) => c.setSeed(e.target.value === "" ? null : Math.max(0, Math.round(Number(e.target.value))))} /></span>
        </label>
      </div>
      <span className="meta">Defensa</span>
      <div className="seg" role="group" aria-label="Defensa">
        {DEFENSES.map(([d, short, name]) => (
          <button key={d} className={c.defense === d ? "on" : ""} aria-pressed={c.defense === d} data-tip={name}
            disabled={d === "llm" && !c.llmAvailable} onClick={() => c.setDefense(d)}>{short}</button>
        ))}
      </div>
      <p className="meta">{c.defense === "llm" ? "El comandante usa el modelo del servidor y solo elige entre acciones ya validadas; si no responde, sigue la política C." : c.llmAvailable ? "Política por reglas sobre los recursos disponibles." : "Política por reglas. El comandante LLM no está activo en este servidor."}</p>
      <button className="btn cy-go" disabled={c.busy} onClick={() => void c.launch()}>{c.busy ? "Simulando…" : "Iniciar ciberataque"}</button>
      <p className="meta">Corre sobre la red base (nodos originales, nov. 2026 13:00) en una sesión nueva. Necesita el backend.</p>
    </div>
  );
}

function Result({ c }: { c: Cyber }) {
  const run = c.run!;
  const areas = c.catalog?.areas ?? [];
  const name = (id: string) => areas.find((a) => a.id === id)?.name ?? id;
  const f = run.frames[c.at];
  const outcome = run.report?.outcome ?? f?.outcome;
  return (
    <>
      <div className="card">
        <div className="card-head">
          <h3>{outcome ? OUTCOME_LABEL[outcome] : c.busy ? "Simulando…" : "En curso"}</h3>
          <button className="text-btn" onClick={c.close}>Cerrar</button>
        </div>
        <p className="meta">Defensa {run.llm ? "LLM" : c.defense}{run.seed != null ? ` · semilla ${run.seed}` : ""}{run.report?.start_area ? ` · inicio en ${name(run.report.start_area)}` : ""}{run.report ? ` · máximo ${run.report.peak_active_areas} áreas con intrusión` : ""}</p>
      </div>

      {f && (
        <div className="card">
          <div className="card-head"><h3>Ciclo {f.cycle}</h3><span className="unit">min {f.t_min}</span></div>
          <div className="cy-controls">
            {c.playing ? <button className="btn" onClick={c.pause}>Pausa</button> : <button className="btn" onClick={c.play}>Reproducir</button>}
            <input type="range" min={0} max={run.frames.length - 1} value={c.at} onChange={(e) => c.seek(Number(e.target.value))} aria-label="Ciclo" />
            {f.transient && (c.mapCycle === f.cycle
              ? <button className="text-btn" onClick={() => c.showOnMap(null)}>Quitar del mapa</button>
              : <button className="btn" onClick={() => c.showOnMap(f.cycle)}>Ver cascada en el mapa</button>)}
          </div>
          <div className="mini-figures cy-figures">
            {frameFigures(f).map((x) => <div key={x.label}><b>{x.value}</b><span>{x.label}</span></div>)}
          </div>
          <div className="cy-areas" role="list" aria-label="Áreas operativas">
            {areas.map((a) => {
              const st: AreaState = f.areas[a.id] ?? "clean";
              return <div key={a.id} role="listitem" className={`cy-area ${st}`} title={`${a.name}: ${STATE_LABEL[st]}`}><b>{a.id}</b><span>{a.name}</span><em>{STATE_LABEL[st]}</em></div>;
            })}
          </div>
          {!!f.events.length && <ul className="cy-events">{f.events.map((e, i) => <li key={i}>{eventText(e, name)}</li>)}</ul>}
        </div>
      )}

      <div className="card">
        <div className="card-head"><h3>Leyenda</h3></div>
        <div className="cy-legend">{(Object.keys(STATE_LABEL) as AreaState[]).map((s) => <span key={s} className={`cy-area ${s}`}><em>{STATE_LABEL[s]}</em></span>)}</div>
        <p className="meta">Valores del modelo, no una predicción (is_assumption). La defensa ve solo lo que muestra la supervisión.</p>
      </div>
    </>
  );
}
