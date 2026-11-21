import type { Layer, PickingInfo } from "@deck.gl/core";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { FrequencyChart } from "../cascade/FrequencyChart";
import { formatPeople, lineName, narrate } from "../cascade/text";
import type { Frame } from "../cascade/types";
import type { ViewMode } from "../map/baseMap";
import { connect, type TheaterSource } from "./api";
import { buildOperationLayers, CREW_BUSY_COLOR, CREW_COLOR, POSTURE_COLOR, POSTURE_LABEL } from "./layers";
import { actionText, clock, decisionText, eventLabel, label, notice, pct, SOURCE_LABEL, verdictText } from "./text";
import type { AfterAction, Catalog, Crew, LlmNote, Narrative, Posture, Report, RunSummary, TheaterArea, TheaterNetwork, TheaterSnapshot } from "./types";

const CYCLE_MS = 1200;
const STAGE_MS = 1400;
const NODE_EVENTS = [
  { type: "C1_generation_loss", text: "Pérdida de generación" },
  { type: "D1_telemetry_loss", text: "Pérdida de telemetría" },
  { type: "D4_comms_loss", text: "Pérdida de comunicaciones" },
];

/** What the shared map asks the active panel for: layers each animation frame, clicks and tooltips. */
export interface MapBridge {
  layers(time: number, mode: ViewMode): Layer[] | null;
  onClick(info: PickingInfo): void;
  tooltip(info: PickingInfo): string | null;
}

/** Operation mode of mapa 3: the strategic theatre (5-minute cycles) on the same map as the cut viewer. */
export function OperationPanel({ pointId, bridge }: { pointId: string; bridge: React.MutableRefObject<MapBridge | null> }) {
  const [source, setSource] = useState<TheaterSource | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [nar, setNar] = useState<Narrative | null>(null);
  const [network, setNetwork] = useState<TheaterNetwork | null>(null);
  const [template, setTemplate] = useState("flagship_observability");
  const [policy, setPolicy] = useState("C");
  const [adaptive, setAdaptive] = useState(true);
  const [useAi, setUseAi] = useState(true);
  const [thinking, setThinking] = useState(false);
  const [run, setRun] = useState<RunSummary | null>(null);
  const [snaps, setSnaps] = useState<TheaterSnapshot[]>([]);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [stage, setStage] = useState<number | null>(null); // replaying the cycle's cascade (seconds)
  const [report, setReport] = useState<{ report: Report; aar: AfterAction } | null>(null);
  const [busMenu, setBusMenu] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);

  useEffect(() => {
    connect().then(async (s) => {
      setSource(s);
      const [c, n] = await Promise.all([s.catalog(), s.narrative()]);
      setCatalog(c);
      setNar(n);
    }).catch((e) => setError(String(e.message)));
  }, []);
  useEffect(() => {
    if (!source) return;
    setNetwork(null);
    source.network(pointId).then(setNetwork).catch((e) => setError(String(e.message)));
    _reset();
  }, [source, pointId]);

  const snap = snaps[Math.min(idx, snaps.length - 1)];
  const aiOn = useAi && !!source?.live && !!catalog?.llm?.available;
  const finished = run?.status === "finished" && idx >= snaps.length - 1;
  const dispatched = useMemo(() => {
    const out: Record<string, number> = {};
    for (const s of snaps.slice(0, idx + 1)) for (const e of s.executed) if (e.crew) out[e.crew] = s.cycle;
    return out;
  }, [snaps, idx]);

  // the shared map reads the latest state through this bridge
  const state = useRef({ network, snap, stage, dispatched, busMenu });
  state.current = { network, snap, stage, dispatched, busMenu };
  useEffect(() => {
    bridge.current = {
      layers: (time, mode) => {
        const { network: net, snap: s, stage: st, dispatched: d, busMenu: bm } = state.current;
        if (!net || !s) return null;
        const frame: Frame | null = st != null && s.transient ? s.transient.frames[Math.min(st, s.transient.frames.length - 1)] : s.grid;
        return frame ? buildOperationLayers({ network: net, snapshot: s, frame, time, selected: bm, mode, dispatched: d }) : null;
      },
      onClick: (info) => _click(info),
      tooltip: (info) => _tooltip(info),
    };
    return () => { bridge.current = null; };
  });

  useEffect(() => {  // play cycles: show the next computed one, or compute it live
    if (!playing) return;
    const id = setInterval(() => _next(), CYCLE_MS);
    return () => clearInterval(id);
  });
  useEffect(() => {  // replay the cascade of the cycle, stage by stage
    if (stage == null || !snap?.transient) return;
    const last = snap.transient.frames.length - 1;
    if (stage >= last) return;
    const id = setTimeout(() => setStage((x) => (x == null ? null : x + 1)), STAGE_MS);
    return () => clearTimeout(id);
  }, [stage, snap]);
  useEffect(() => {
    if (finished && run && source && !report) {
      Promise.all([source.report(run.run_id), source.afterAction(run.run_id)])
        .then(([r, a]) => setReport({ report: r, aar: a })).catch((e) => setError(String(e.message)));
    }
  }, [finished, run, source, report]);

  function _reset() {
    setRun(null); setSnaps([]); setIdx(0); setPlaying(false); setStage(null); setReport(null); setBusMenu(null); setMsg(null);
  }

  async function _start() {
    if (!source || !catalog) return;
    _reset(); setError(null);
    const tpl = catalog.templates.find((t) => t.id === template);
    const adversary = tpl?.adversary.enabled ? { ...tpl.adversary, adaptive } : undefined;
    try {
      const r = await source.create({ template, policy, point: pointId, adversary, llm_commander: aiOn });
      setRun(r);
      setThinking(aiOn);
      const first = await source.step(r.run_id, 1).finally(() => setThinking(false));
      setRun(first.run); setSnaps(first.snapshots); setIdx(0);
    } catch (e) { setError(String((e as Error).message)); }
  }

  async function _next() {
    if (!source || !run || busy.current) return;
    setStage(null);
    if (idx < snaps.length - 1) { setIdx(idx + 1); return; }
    if (run.status === "finished") { setPlaying(false); return; }
    busy.current = true;
    setThinking(aiOn);
    try {
      const r = await source.step(run.run_id, 1);
      setRun(r.run);
      if (r.snapshots.length) { setSnaps((s) => [...s, ...r.snapshots]); setIdx(snaps.length); }
      if (r.run.status === "finished") setPlaying(false);
    } catch (e) { setError(String((e as Error).message)); setPlaying(false); }
    finally { busy.current = false; setThinking(false); }
  }

  async function _replay(other: string) {
    if (!source || !run) return;
    setError(null);
    try {
      const r = await source.replay(run.run_id, { policy: other });
      const computed = await source.snapshots(r.run_id, 0);
      setPolicy(other); setReport(null); setStage(null); setBusMenu(null);
      setRun(r); setSnaps(computed); setIdx(0);
      if (!computed.length) { const first = await source.step(r.run_id, 1); setRun(first.run); setSnaps(first.snapshots); }
      setPlaying(true);
      setMsg(`Misma semilla (${r.seed}), política ${other}: compara el resultado.`);
    } catch (e) { setError(String((e as Error).message)); }
  }

  async function _inject(type: string, target: string) {
    if (!source || !run) return;
    setBusMenu(null);
    if (!source.live) { setMsg("Sin servidor: es una corrida precalculada, no se pueden disparar eventos."); return; }
    if (run.status === "finished") { setMsg("La corrida terminó: inicia otra o repítela con otra política."); return; }
    try {
      const r = await source.inject(run.run_id, type, target);
      setMsg(`${eventLabel(nar, type)} en ${r.resolved_target}${r.area ? ` (${r.area})` : ""}: se aplica en el próximo ciclo.`);
    } catch (e) { setError(String((e as Error).message)); }
  }

  function _click(info: PickingInfo) {
    if (!run || !info.object) return;
    const id = (info.object as { id: string }).id;
    if (info.layer?.id === "lines") _inject("C3_transmission_opening", id);
    else if (info.layer?.id === "nodes") setBusMenu(id);
  }

  function _tooltip(info: PickingInfo): string | null {
    const { network: net, snap: s } = state.current;
    if (!info.object || !net) return null;
    const layer = info.layer?.id;
    if (layer === "areas") {
      const a = info.object as TheaterArea;
      const st = s?.areas[a.id];
      const effects = st?.effects.map((e) => eventLabel(nar, e.type)).join(", ");
      return `${a.id} · ${a.name}\n${POSTURE_LABEL[(st?.posture ?? "normal") as Posture]} · supervisión ${Math.round((st?.observability ?? 1) * 100)}%${effects ? `\n${effects}` : ""}`;
    }
    if (layer === "crews") return _crewText(info.object as Crew, s?.cycle ?? 0, net);
    if (layer === "lines") {
      const id = (info.object as { id: string }).id;
      const e = s?.grid?.edges[id];
      return `${lineName(net, id)}\n${e ? `${e.flow_mw} MW · ${Math.round(e.loading * 100)}%` : "sin flujo"}${run ? "\nClic: abrir esta línea en el próximo ciclo" : ""}`;
    }
    const node = info.object as { id: string; name: string; area?: string };
    const served = s?.grid?.buses[node.id];
    const dark = s?.grid?.dark.includes(node.id);
    return `${node.name}${node.area ? ` · ${node.area}` : ""}${served != null ? `\n${Math.round(served)} MW servidos` : ""}${dark ? "\nSin energía" : ""}${run ? "\nClic: disparar un evento aquí" : ""}`;
  }

  if (error && !source) return <p className="note warn">{error}</p>;
  const m = snap?.metrics;
  const aiChosen = new Set(snap?.llm?.chosen ?? []);
  const tpl = catalog?.templates.find((t) => t.id === template);
  return (
    <section className="operation">
      {source && !source.live && <p className="note">Sin servidor: corridas precalculadas (semilla fija, sin eventos propios).</p>}
      {error && <p className="note warn">{error}</p>}
      <p className="muted">{notice(nar)}</p>

      <div className="op-config">
        <label className="field">Escenario
          <select value={template} onChange={(e) => setTemplate(e.target.value)}>
            {catalog?.templates.map((t) => <option key={t.id} value={t.id}>{label(nar, t.label_key)}</option>)}
          </select>
        </label>
        <label className="field">Política de defensa
          <select value={policy} onChange={(e) => setPolicy(e.target.value)}>
            {catalog?.policies.map((p) => <option key={p.id} value={p.id}>{label(nar, p.label_key)}</option>)}
          </select>
        </label>
        {source?.live && catalog?.llm?.available && (
          <label className="check ai"><input type="checkbox" checked={useAi} onChange={(e) => setUseAi(e.target.checked)} /> Comandante con IA <code>{catalog.llm.model}</code></label>
        )}
        {tpl?.adversary.enabled && (
          <label className="check"><input type="checkbox" checked={adaptive} onChange={(e) => setAdaptive(e.target.checked)} /> Adversario adaptativo ({label(nar, tpl.adversary.objective)})</label>
        )}
        <button onClick={_start} disabled={!catalog || !network}>{run ? "Nueva corrida" : "Iniciar corrida"}</button>
      </div>

      {run && snap && m && (
        <>
          <p className="muted">Semilla {run.seed} · {run.operating_point} · política {run.policy}{run.replay_of ? " (repetición)" : ""}</p>
          <div className="stats">
            <div><b>{pct(m.served_mw / Math.max(1, m.demand_mw))}</b><span>servicio</span></div>
            <div><b>{formatPeople(Math.round(m.people_without_power))}</b><span>personas sin luz</span></div>
            <div><b>{snap.real.worst_level}</b><span>peor nivel</span></div>
          </div>
          <div className="player">
            <button onClick={() => setPlaying(!playing)} disabled={finished}>{playing ? "Pausa" : "Reproducir"}</button>
            <button onClick={() => _next()} disabled={playing || finished}>+1 ciclo</button>
            <input type="range" min={0} max={Math.max(0, snaps.length - 1)} value={idx} onChange={(e) => { setPlaying(false); setStage(null); setIdx(Number(e.target.value)); }} />
            <span>Ciclo {snap.cycle} / {run.horizon} · t = {clock(snap.t_min)}</span>
          </div>
          {msg && <p className="note">{msg}</p>}
          {busMenu && (
            <div className="op-menu">
              <span>Evento en {network?.nodes.find((n) => n.id === busMenu)?.name ?? busMenu}:</span>
              {NODE_EVENTS.map((e) => <button key={e.type} onClick={() => _inject(e.type, busMenu)}>{e.text}</button>)}
              <button onClick={() => setBusMenu(null)}>Cancelar</button>
            </div>
          )}

          {snap.transient && (
            <div className="op-transient">
              <button onClick={() => setStage(stage == null ? 0 : null)}>{stage == null ? `Ver cascada (${snap.transient.frames.length - 1} ${snap.transient.frames.length - 1 === 1 ? "etapa" : "etapas"}, segundos)` : "Volver al ciclo"}</button>
              {stage != null && network && (
                <>
                  <p className="muted">Etapa {stage} / {snap.transient.frames.length - 1} · {formatPeople(snap.transient.summary.people_without_power)} personas sin luz</p>
                  <ol className="events">{snap.transient.events.filter((e) => e.t <= (snap.transient!.frames[stage]?.t ?? 0) + 1).map((e, i) => <li key={i}><span className="t">{e.t.toFixed(1)} s</span> {narrate(e, network)}</li>)}</ol>
                  <FrequencyChart curves={snap.transient.frequency_hz} />
                </>
              )}
            </div>
          )}

          {(snap.llm || thinking) && <AiCard note={snap.llm ?? null} thinking={thinking} nar={nar} />}
          {createPortal(<MapHud snap={snap} run={run} nar={nar} thinking={thinking} stage={stage} />, document.body)}

          <h3>En este ciclo</h3>
          <ul className="op-list">
            {snap.events.map((e) => <li key={e.effect}><b>{SOURCE_LABEL[e.source]}</b> · {eventLabel(nar, e.type)} en {e.area ?? e.target}{e.status !== "established" ? " (bloqueado)" : ""}</li>)}
            {snap.executed.map((e, i) => <li key={`x${i}`} className={e.ok ? "" : "warn"}>{aiChosen.has(`${e.action}:${e.target}`) && <span className="badge ai">IA</span>}{actionText(nar, e.action, e.target)}{e.crew ? ` · cuadrilla ${e.crew}, llega en el ciclo ${e.arrival}` : ""}{e.ok ? "" : ` · ${verdictText(nar, e.verdict)}`}</li>)}
            {!snap.events.length && !snap.executed.length && <li className="muted">Sin eventos ni acciones.</li>}
          </ul>
          <p className="muted">ISR: causa {snap.estimated.isr.leading_cause} ({Math.round(snap.estimated.isr.confidence * 100)}%) · áreas afectadas {snap.estimated.isr.affected.join(", ") || "ninguna"}</p>
          <details><summary>Decisiones de C2 ({snap.decisions.length})</summary>
            <ul className="op-list">{snap.decisions.map((d, i) => <li key={i} className={d.approved ? "" : "muted"}>{aiChosen.has(`${d.action}:${d.target}`) && <span className="badge ai">IA</span>}{actionText(nar, d.action, d.target)} · {decisionText(nar, d.reason)}</li>)}</ul>
          </details>

          {report && (
            <section className="results">
              <h2>Resultado</h2>
              <div className="stats">
                <div><b>{pct(report.report.indicators.mission_continuity)}</b><span>continuidad (experimental)</span></div>
                <div><b>{report.report.consequence.worst_level}</b><span>peor nivel</span></div>
                <div><b>{report.report.indicators.wrong_decisions}</b><span>decisiones innecesarias</span></div>
              </div>
              <ul className="op-list">{report.aar.summary.map((l) => <li key={l}>{l}</li>)}</ul>
              {report.aar.narrative && <p>{report.aar.narrative}</p>}
              <div className="op-replay">Repetir con la misma semilla y otra política:
                {(catalog?.policies ?? []).filter((p) => p.id !== run.policy).map((p) => <button key={p.id} onClick={() => _replay(p.id)}>{label(nar, p.label_key)}</button>)}
              </div>
            </section>
          )}
          <OperationLegend />
        </>
      )}
    </section>
  );
}

function _crewText(c: Crew, cycle: number, net: TheaterNetwork): string {
  const target = c.target ? (net.areas.find((a) => a.id === c.target)?.name ?? c.target) : null;
  const eta = c.arrival != null && c.arrival > cycle ? `llega en ${c.arrival - cycle} ciclos` : "en terreno";
  return `Cuadrilla ${c.id} · base ${c.base}${c.status === "busy" && target ? `\nRumbo a ${target} · ${eta}` : "\nDisponible"}`;
}

const css = (c: number[]) => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${(c[3] ?? 255) / 255})`;

function OperationLegend() {
  return (
    <details className="legend">
      <summary>Qué muestra el mapa en operación</summary>
      <p className="muted">Cada círculo es un área de operación (grupo de subestaciones). Más opaco = la supervisión ve menos.</p>
      {(Object.keys(POSTURE_COLOR) as Posture[]).map((p) => (
        <div key={p} className="legend-row"><span className="legend-swatch"><span className="dot big" style={{ background: css(POSTURE_COLOR[p]) }} /></span><span>{POSTURE_LABEL[p]}</span></div>
      ))}
      <div className="legend-row"><span className="legend-swatch"><span className="dot big" style={{ background: css(CREW_COLOR) }} /></span><span>Cuadrilla disponible</span></div>
      <div className="legend-row"><span className="legend-swatch"><span className="dot big" style={{ background: css(CREW_BUSY_COLOR) }} /></span><span>Cuadrilla en camino o trabajando</span></div>
      <p className="muted">Líneas, subestaciones y demanda se leen igual que en la pestaña Corte.</p>
    </details>
  );
}

/** C2 with the LLM this cycle: which validated options it picked and why, or why it fell back to the rules. */
function AiCard({ note, thinking, nar }: { note: LlmNote | null; thinking: boolean; nar: Narrative | null }) {
  const model = note?.model ?? "";
  if (thinking) return <div className="ai-card thinking"><div className="ai-head"><span className="ai-dot" /> Comandante IA pensando… <code>{model}</code></div></div>;
  if (!note) return null;
  if (note.status === "unavailable") return <div className="ai-card off"><div className="ai-head">Comandante IA no disponible: decidieron las reglas <code>{model}</code></div></div>;
  if (note.status === "idle") return <div className="ai-card idle"><div className="ai-head">Comandante IA · sin opciones que elegir en este ciclo <code>{model}</code></div></div>;
  return (
    <div className="ai-card">
      <div className="ai-head"><span className="badge ai">IA</span> Comandante C2 {note.status === "replayed" ? "(decisión grabada)" : ""} <code>{model}</code></div>
      <p className="ai-choice">Eligió {note.chosen?.length ?? 0} de {note.options ?? "?"} opciones válidas:</p>
      <ul className="op-list">{(note.chosen ?? []).map((k) => { const [a, t] = k.split(":"); return <li key={k}>{actionText(nar, a, t)}</li>; })}</ul>
      {note.explanation && <blockquote className="ai-why">“{note.explanation}”</blockquote>}
    </div>
  );
}

/** Big overlay on the map: clock, service, what happened this cycle and what C2 (AI or rules) did. */
function MapHud({ snap, run, nar, thinking, stage }: { snap: TheaterSnapshot; run: RunSummary; nar: Narrative | null; thinking: boolean; stage: number | null }) {
  const m = snap.metrics;
  const service = m.served_mw / Math.max(1, m.demand_mw);
  const ai = new Set(snap.llm?.chosen ?? []);
  const done = snap.executed.filter((e) => e.ok);
  return (
    <div className="map-hud">
      <div className="hud-top">
        <div className="hud-clock">{clock(snap.t_min)}<span>ciclo {snap.cycle} / {run.horizon}</span></div>
        <div className={`hud-service ${service < 0.95 ? "bad" : ""}`}>{pct(service)}<span>servicio</span></div>
        <div className="hud-level">{snap.real.worst_level}<span>nivel</span></div>
      </div>
      {stage != null && snap.transient && <div className="hud-cascade">Cascada del ciclo · etapa {stage} / {snap.transient.frames.length - 1}</div>}
      <ul className="hud-events">
        {snap.events.map((e) => <li key={e.effect} className={`src-${e.source}`}><b>{SOURCE_LABEL[e.source]}</b> {eventLabel(nar, e.type)} · {e.area ?? e.target}</li>)}
        {done.slice(0, 4).map((e, i) => <li key={`d${i}`} className={ai.has(`${e.action}:${e.target}`) ? "src-ai" : "src-c2"}><b>{ai.has(`${e.action}:${e.target}`) ? "C2 · IA" : "C2"}</b> {actionText(nar, e.action, e.target)}</li>)}
      </ul>
      {thinking && <div className="hud-thinking"><span className="ai-dot" /> El comandante IA está decidiendo…</div>}
      {!thinking && snap.llm?.status === "chosen" && snap.llm.explanation && <div className="hud-ai">“{snap.llm.explanation}”</div>}
    </div>
  );
}
