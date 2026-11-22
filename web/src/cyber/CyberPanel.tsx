import { useEffect, useState, type ReactNode } from "react";
import {
  actionText, activePreset, cycleClock, cycleMarks, DEFENSE_NAME, DEFENSES, eventText, FIELDS, healthRows, millions, NOTICE, OUTCOME_LABEL,
  scoreboard, shown, SIDE, statusOf, STATUS_LABEL, stored, type CyberArea, type CyberFrame, type Status,
} from "./cyber";
import type { CycleRun } from "../cascade/Timeline";
import { Info } from "../cascade/ui";
import type { Cyber, Sub } from "./useCyber";
import "./cyber.css";

/**
 * The Ciberataque monitor. One layout for every defender (algorithm, LLM commander or the user): the attack's and the
 * defence's counters, the operating areas with their people and state, the cycle bar, and labels on the map. The form
 * comes from `GET /sim/catalog` → `cyber_attack`; the run and every number come from the backend. Area level only.
 */
export function CyberPanel({ c, component, prefault }: { c: Cyber; component: ReactNode; prefault: ReactNode }) {
  useEffect(() => { c.load(); }, []);
  return (
    <div className="cyber">
      {c.error && <p className="note">{c.error}</p>}
      {!c.catalog && !c.error && <p className="meta">Cargando el escenario…</p>}
      {c.catalog && !c.run && <Form c={c} />}
      {c.run && <Monitor c={c} component={component} prefault={prefault} />}
    </div>
  );
}

function Form({ c }: { c: Cyber }) {
  const cat = c.catalog!;
  return (
    <>
      <div className="card">
        <div className="card-head"><h3>Ciberataque simulado</h3></div>
        <p className="meta">Una intrusión aparece en un área operativa al azar y salta a las vecinas. Un área comprometida, al rato, pierde el despacho remoto y parte de su generación, y la red responde con su cascada real. La defensa segmenta y repara con cuadrillas limitadas. Gana el ataque si la red pierde el umbral de demanda; gana la defensa si no queda intrusión y todo se reparó.</p>
      </div>
      <div className="notice"><span>{NOTICE}</span></div>
      <div className="card">
        <div className="card-head"><h3>Quién defiende</h3></div>
        <div className="seg" role="group" aria-label="Defensa">
          {DEFENSES.map(([d, short, name]) => (
            <button key={d} className={c.defense === d ? "on" : ""} aria-pressed={c.defense === d} data-tip={name}
              disabled={d === "llm" && !c.llmAvailable} onClick={() => c.setDefense(d)}>{short}</button>
          ))}
        </div>
        <p className="meta">{c.defense === "user" ? "Juegas tú: en cada turno eliges acciones por área y terminas el turno; el ataque juega después."
          : c.defense === "llm" ? "El comandante usa el modelo del servidor y solo elige entre acciones ya validadas; si no responde, sigue el algoritmo C."
            : `Algoritmo por reglas sobre los recursos disponibles.${c.llmAvailable ? "" : " El comandante LLM no está activo en este servidor."}`}</p>
      </div>
      <div className="card">
        <div className="card-head"><h3>Dificultad</h3><span className="unit">supuestos, ciclos de 5 min</span></div>
        {!!cat.presets?.length && (() => {
          const on = activePreset(cat, c.params);
          return (
            <>
              <div className="seg" role="group" aria-label="Dificultad">
                {cat.presets!.map((p) => (
                  <button key={p.id} className={on?.id === p.id ? "on" : ""} aria-pressed={on?.id === p.id} data-tip={p.measured}
                    onClick={() => Object.entries(p.params).forEach(([k, v]) => c.setParam(k, v))}>{p.label}</button>
                ))}
              </div>
              <p className="meta">{on ? `${on.label}. Medido: ${on.measured ?? "sin medición"}.` : "Valores a mano: ajusta cada parámetro abajo."}</p>
            </>
          );
        })()}
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
          <label className="cy-field"><span>Cuadrillas de terreno</span>
            <span className="cy-input"><input type="number" min={0} max={60} step={1} value={c.crews} onChange={(e) => c.setCrews(Math.max(0, Math.round(Number(e.target.value))))} /></span></label>
          <label className="cy-field"><span>Semilla (vacía: al azar)</span>
            <span className="cy-input"><input type="number" min={0} step={1} value={c.seed ?? ""} onChange={(e) => c.setSeed(e.target.value === "" ? null : Math.max(0, Math.round(Number(e.target.value))))} /></span></label>
        </div>
        <button className="btn cy-go" disabled={c.busy} onClick={() => void c.launch()}>{c.busy ? "Preparando…" : "Iniciar ciberataque"}</button>
        <p className="meta">Corre sobre la red base (nodos originales, nov. 2026 13:00) en una sesión nueva. Necesita el backend.</p>
      </div>
    </>
  );
}

const SUBS: [Sub, string][] = [["territorio", "Territorio"], ["jugadas", "Jugadas"], ["componente", "Componente"], ["salud", "Salud de la red"], ["reglas", "Reglas"]];

function Monitor({ c, component, prefault }: { c: Cyber; component: ReactNode; prefault: ReactNode }) {
  const run = c.run!;
  const areas = c.catalog?.areas ?? [];
  const name = (id: string) => areas.find((a) => a.id === id)?.name ?? id;
  const f = run.frames[c.at];
  const outcome = run.report?.outcome ?? f?.outcome ?? null;
  const user = run.defense === "user";
  return (
    <>
      <div className="cy-head">
        <div className="cy-title">
          <h3>Ataque vs defensa <span>{DEFENSE_NAME[run.defense]}{run.seed != null ? ` · semilla ${run.seed}` : ""}</span></h3>
          <button className="text-btn" onClick={c.close}>Nueva partida</button>
        </div>
        <div className="cy-subtabs" role="tablist">
          {SUBS.map(([k, label]) => (
            <button key={k} role="tab" aria-selected={c.sub === k} className={c.sub === k ? "on" : ""} onClick={() => c.setSub(k)}>{label}</button>
          ))}
        </div>
      </div>
      {outcome && <div className={`cy-outcome ${outcome}`}>{OUTCOME_LABEL[outcome]}</div>}
      {!f && <p className="meta">Simulando el primer ciclo…</p>}
      {f && c.sub === "territorio" && <Territory c={c} f={f} areas={areas} />}
      {f && c.sub === "jugadas" && <Plays run={run.frames} upto={c.at} name={name} hideLatent={user && !run.finished} />}
      {c.sub === "componente" && (component ?? <p className="meta">Haz clic en una línea o una subestación del mapa para ver sus datos aquí, en el ciclo que muestra el mapa.</p>)}
      {f && c.sub === "salud" && <Health f={f} prefault={prefault} />}
      {c.sub === "reglas" && <Rules c={c} />}
      {user && !run.finished && c.queued.length > 0 && <p className="meta">En cola para este turno: {c.queued.map((q) => q.label).join(", ")}.</p>}
      <div className="notice"><span>{NOTICE} Valores del modelo, no una predicción.</span></div>
    </>
  );
}

function Health({ f, prefault }: { f: CyberFrame; prefault: ReactNode }) {
  return (
    <>
      <div className="card">
        <div className="card-head"><h3>Salud de la red · ciclo {f.cycle}</h3><span className="unit">min {f.t_min}</span></div>
        <div className="mini-figures cy-figures">
          {healthRows(f).map((r) => <div key={r.label}><span className="value-row"><b>{r.value}</b><Info tip={r.tip} /></span><span>{r.label}</span></div>)}
        </div>
      </div>
      {prefault && <div className="card"><div className="card-head"><h3>Antes del ataque</h3></div>{prefault}</div>}
    </>
  );
}

function Territory({ c, f, areas }: { c: Cyber; f: CyberFrame; areas: CyberArea[] }) {
  const user = c.run!.defense === "user" && !c.run!.finished;
  const s = scoreboard(f, areas, user); // the user defends with what supervision shows: latent areas stay hidden
  const [open, setOpen] = useState<string | null>(null);
  const actions = c.catalog?.defense_actions ?? [];
  return (
    <>
      <div className="cy-score">
        <div className="cy-side attack">
          <span className="cy-who"><i />ataque</span>
          <b>{s.attackAreas}<small> áreas apagadas o afectadas</small></b>
          <span className="meta">{millions(s.peopleOut)} personas sin luz{s.disputed ? ` · ${s.disputed} en disputa` : ""}</span>
        </div>
        <div className="cy-side defense">
          <span className="cy-who"><i />defensa · {DEFENSE_NAME[c.run!.defense]}</span>
          <b>{s.defenseAreas}<small> áreas blindadas</small></b>
          <span className="meta">{millions(s.protectedPeople)} personas protegidas</span>
        </div>
      </div>
      <div className="card cy-regions">
        <div className="card-head"><h3>Áreas operativas</h3><span className="unit">personas</span></div>
        <ul>
          {areas.map((a) => {
            const st = statusOf(f, a.id, user);
            const out = f.people_out?.[a.id] ?? 0;
            return (
              <li key={a.id} className={open === a.id ? "on" : ""}>
                <button className="cy-row" disabled={!user} onClick={() => setOpen(open === a.id ? null : a.id)} aria-expanded={user ? open === a.id : undefined}>
                  <span className={`cy-sw ${st}`} /><span className="cy-name">{a.name}</span>
                  <span className="cy-pop">{millions(a.population)}</span>
                  <span className={`cy-st ${st}`} title={out > 0 ? `${millions(out)} sin luz` : undefined}>{STATUS_LABEL[st]}</span>
                </button>
                {user && open === a.id && (
                  <div className="cy-acts">
                    {actions.map((x) => (
                      <button key={x.action} className="btn" disabled={c.busy || c.queued.some((q) => q.action === x.action && q.target === a.id)}
                        onClick={() => void c.queue(x.action, a.id, `${x.label} ${a.name}`)}>{x.label}</button>
                    ))}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </>
  );
}

function Plays({ run, upto, name, hideLatent }: { run: CyberFrame[]; upto: number; name: (id: string) => string; hideLatent: boolean }) {
  // a user defending sees what supervision sees: silent jumps show up once the run ends
  const seen = (f: CyberFrame) => (hideLatent ? f.events.filter((e) => e.kind !== "compromised") : f.events);
  const rows = run.slice(0, upto + 1).filter((f) => seen(f).length || f.defense_actions?.length).reverse();
  return (
    <div className="card">
      <div className="card-head"><h3>Jugadas</h3><span className="unit">más reciente primero</span></div>
      {!rows.length && <p className="meta">Todavía no hay jugadas.</p>}
      <ol className="cy-plays">
        {rows.map((f) => (
          <li key={f.cycle}>
            <b>Ciclo {f.cycle}</b><span className="meta"> · min {f.t_min}</span>
            <ul>
              {seen(f).map((e, i) => <li key={`e${i}`} className="atk">{eventText(e, name)}</li>)}
              {(f.defense_actions ?? []).map((d, i) => <li key={`d${i}`} className={d.ok ? "def" : "def failed"}>{actionText(d, name)}</li>)}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Rules({ c }: { c: Cyber }) {
  const run = c.run!;
  const p = run.report?.params ?? c.params;
  return (
    <div className="card">
      <div className="card-head"><h3>Reglas de esta partida</h3><span className="unit">supuestos</span></div>
      <ul className="cy-rules">
        {FIELDS.filter((f) => f.key in p).map((f) => <li key={f.key}><span>{f.label}</span><b>{f.unit === "ciclos" ? `${p[f.key]} ciclos` : `${Math.round(p[f.key] * 100)} %`}</b></li>)}
        <li><span>Cuadrillas de terreno</span><b>{c.crews}</b></li>
        {run.seed != null && <li><span>Semilla</span><b>{run.seed}</b></li>}
      </ul>
      <p className="meta">El ataque no elige objetivos: parte en un área al azar y salta a vecinas por probabilidad. Cada acción de la defensa pasa por el mismo validador y gasta las mismas cuadrillas, la juegue un algoritmo, el LLM o tú.</p>
    </div>
  );
}

/** Labels of the operating areas on the map, one per area at its anchor substation; the overlay loop places them. */
export function CyberMapTags({ c }: { c: Cyber }) {
  const f = c.run?.frames[c.at];
  if (!f || !c.catalog) return null;
  const hide = c.run!.defense === "user" && !c.run!.finished;
  return (
    <>
      {c.catalog.areas.filter((a) => a.lon != null && a.lat != null).map((a) => {
        const st: Status = statusOf(f, a.id, hide);
        return (
          <div key={a.id} className={`anchor cy-tag-anchor ${SIDE[st]} ${st}`} data-lon={a.lon!} data-lat={a.lat!}>
            <span className="cy-dot" />
            <svg className="cy-lead" width="1" height="1" aria-hidden><line x1="0" y1="0" x2="0" y2="0" /></svg>
            <span className="cy-tag">{st === "shielded" && <i className="cy-tag-shield" />}{a.name}{st === "compromised" && <em> en disputa</em>}</span>
          </div>
        );
      })}
    </>
  );
}

/**
 * The bottom timeline card in cycle mode for the run on screen: the same card that plays a cascade second by second
 * plays the attack cycle by cycle. With the user defending, Terminar turno sits in the card; a cycle with a cascade
 * offers to play it on the map.
 */
export function cyberCycles(c: Cyber): CycleRun | null {
  const run = c.run;
  const f = run?.frames[c.at];
  if (!run || !f) return null;
  const areas = c.catalog?.areas ?? [];
  const name = (id: string) => areas.find((a) => a.id === id)?.name ?? id;
  const last = run.frames.length - 1;
  const user = run.defense === "user";
  const waiting = user && !run.finished && c.at === last;
  const status = run.finished ? `terminó en el ciclo ${run.frames[last].cycle}`
    : waiting ? `turno ${f.cycle + 1}: juega la defensa`
      : c.playing ? "en curso" : "en pausa";
  const action = waiting
    ? <button className="btn" disabled={c.busy} onClick={() => void c.endTurn()}>{c.busy ? "Jugando…" : "Terminar turno"}</button>
    : f.transient
      ? (c.mapCycle === f.cycle
        ? <button className="text-btn" onClick={() => c.showOnMap(null)}>Volver a la red</button>
        : <button className="text-btn" onClick={() => c.showOnMap(f.cycle)}>Ver cascada</button>)
      : undefined;
  return {
    clock: cycleClock(f.t_min), status, played: run.frames.length ? run.frames[last].cycle + 1 : 0, total: run.horizon, at: f.cycle,
    playing: c.playing, finished: run.finished, marks: cycleMarks(run.frames, name, user && !run.finished),
    togglePlay: user && !run.finished ? () => void c.endTurn() : c.togglePlay,
    seek: (cycle) => { const i = run.frames.findIndex((x) => x.cycle >= cycle); if (i >= 0) c.seek(i); },
    action,
  };
}
