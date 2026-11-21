import type { PickingInfo } from "@deck.gl/core";
import { useEffect, useMemo, useRef, useState } from "react";
import { createBaseMap, type BaseMap, type ViewMode } from "../map/baseMap";
import { loadBuses, loadIndex, loadNetwork, loadTimeline } from "./api";
import { buildCascadeLayers } from "./layers";
import { FrequencyChart } from "./FrequencyChart";
import { CascadeLegend } from "./Legend";
import { NetworkPanel } from "./NetworkPanel";
import { formatPeople, lineName, narrate } from "./text";
import type { BusState, Index, Network, Timeline } from "./types";

type Tab = "red" | "sim" | "legend" | "assumptions";
const TABS: [Tab, string][] = [["red", "Red"], ["sim", "Simulación"], ["legend", "Leyenda"], ["assumptions", "Supuestos"]];
const STAGE_MS = 1400;
const FLOW_PERIOD_S = 3.0;
const FLOW_CYCLE = 1 + 2 / 3;

/** Mapa 3: click a line to cut it and watch the cascade computed by the engine (precomputed in web/public/cache). */
export function CascadeApp() {
  const mapRef = useRef<HTMLDivElement>(null);
  const baseMap = useRef<BaseMap | null>(null);
  const [index, setIndex] = useState<Index | null>(null);
  const params = useMemo(() => new URLSearchParams(location.search), []);  // ?point=<id>&cut=<line id> opens a case directly
  const [pointId, setPointId] = useState(params.get("point") ?? "nov2026-1300");
  const [network, setNetwork] = useState<Network | null>(null);
  const [buses, setBuses] = useState<Record<string, BusState>>({});
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [cut, setCut] = useState<string | null>(params.get("cut"));
  const [stage, setStage] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [tab, setTab] = useState<Tab>("red");
  const [node, setNode] = useState<string | null>(null);
  const [railOpen, setRailOpen] = useState(localStorage.getItem("rail") !== "closed");
  const [mode, setMode] = useState<ViewMode>(params.get("vista") === "2d" ? "2d" : "3d");
  const [error, setError] = useState<string | null>(null);
  const view = useRef({ network, buses, timeline, stage, cut, mode });
  view.current = { network, buses, timeline, stage, cut, mode };

  useEffect(() => { loadIndex().then(setIndex).catch((e) => setError(String(e.message))); }, []);
  useEffect(() => { _loadPoint(); }, [pointId, index]);
  useEffect(() => { _loadTimeline(); }, [pointId, cut, network]);
  useEffect(() => _mountMap(), []);
  useEffect(() => { if (cut) setTab("sim"); }, [cut]);
  useEffect(() => { baseMap.current?.setMode(mode); }, [mode]);
  useEffect(() => _animate(), []);
  useEffect(() => _autoplay(), [playing, timeline]);

  function _loadPoint() {
    const info = index?.points.find((p) => p.id === pointId);
    if (!info) return;
    Promise.all([loadNetwork(info.year), loadBuses(pointId)]).then(([n, b]) => { setNetwork(n); setBuses(b); }).catch((e) => setError(String(e.message)));
  }

  function _loadTimeline() {
    if (!network) return;
    loadTimeline(pointId, cut ?? "baseline").then((t) => { setTimeline(t); setStage(0); setPlaying(!!cut); }).catch((e) => setError(String(e.message)));
  }

  function _mountMap() {
    const map = createBaseMap(mapRef.current!, {
      onClick: (info: PickingInfo) => {
        const id = (info.object as { id: string } | undefined)?.id;
        if (!id) return;
        if (info.layer?.id === "lines") setCut(id);
        else if (info.layer?.id === "nodes" || info.layer?.id === "load" || info.layer?.id === "load-2d") { setNode(id); setTab("red"); }
      },
      getTooltip: (info: PickingInfo) => _tooltip(info),
    });
    baseMap.current = map;
    map.setMode(view.current.mode);
    return () => map.dispose();
  }

  function _tooltip(info: PickingInfo): string | null {
    const { network: net, timeline: tl, stage: s } = view.current;
    if (!info.object || !net) return null;
    if (info.layer?.id === "lines") {
      const id = (info.object as { id: string }).id;
      const e = tl?.frames[s]?.edges[id];
      return `${lineName(net, id)}\n${e ? `${e.flow_mw} MW · ${Math.round(e.loading * 100)}% de su capacidad` : "sin flujo"}\nClic para cortar`;
    }
    const node = info.object as { id: string; name: string; kv: number };
    const b = view.current.buses[node.id];
    const dark = tl?.frames[s]?.dark.includes(node.id);
    return `${node.name}\n${node.kv} kV${b ? ` · ${Math.round(b.load_mw)} MW · ${formatPeople(b.people)} personas` : ""}${dark ? "\nSin energía" : ""}`;
  }

  function _animate() {
    let raf = 0;
    const tick = (now: number) => {
      const v = view.current;
      const frame = v.timeline?.frames[Math.min(v.stage, (v.timeline?.frames.length ?? 1) - 1)];
      if (v.network && frame) {
        const time = ((now / 1000) / FLOW_PERIOD_S) % FLOW_CYCLE;
        baseMap.current?.setLayers(buildCascadeLayers({ network: v.network, buses: v.buses, frame, time, selected: v.cut, mode: v.mode }));
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }

  function _autoplay() {
    if (!playing || !timeline) return;
    const id = setInterval(() => setStage((s) => (s + 1 >= timeline.frames.length ? (setPlaying(false), s) : s + 1)), STAGE_MS);
    return () => clearInterval(id);
  }

  const visibleEvents = useMemo(() => {
    if (!timeline) return [];
    const until = timeline.frames[stage]?.t ?? 0;
    return timeline.events.filter((e) => e.t <= until + 1e-9 || e.t <= until + (timeline.frames[1]?.t ?? 1));
  }, [timeline, stage]);

  const frame = timeline?.frames[Math.min(stage, (timeline?.frames.length ?? 1) - 1)];
  return (
    <div className={railOpen ? "shell" : "shell rail-closed"}>
      <div className="map" ref={mapRef} />
      <nav className={railOpen ? "rail" : "rail collapsed"} aria-label="Navegación">
        <div className="brand"><Icon d="M13 2 4 14h6l-1 8 9-12h-6z" fill /><span className="label">Sub50</span></div>
        <button className="rail-item on" aria-current="page" title="Mapa"><Icon d="M9 3 3 5v16l6-2 6 2 6-2V3l-6 2zM9 3v16M15 5v16" /><span className="label">Mapa</span></button>
        <p className="rail-section label">Referencia</p>
        <button className="rail-item" title="Supuestos" onClick={() => setTab("assumptions")}><Icon d="M6 2h9l4 4v16H6zM14 2v5h5M9 12h7M9 16h7" /><span className="label">Supuestos</span></button>
        <button className="rail-item rail-toggle" aria-label={railOpen ? "Contraer barra lateral" : "Expandir barra lateral"} title={railOpen ? "Contraer" : "Expandir"} onClick={() => { localStorage.setItem("rail", railOpen ? "closed" : "open"); setRailOpen(!railOpen); }}>
          <Icon d={railOpen ? "m15 6-6 6 6 6" : "m9 6 6 6-6 6"} /><span className="label">Contraer</span>
        </button>
      </nav>
      <select className="case-pill" aria-label="Hora del caso base" value={pointId} onChange={(e) => { setCut(null); setPointId(e.target.value); }}>
        {index?.points.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
      </select>
      <div className="map-controls">
        <div className="seg" role="group" aria-label="Vista del mapa">
          {(["2d", "3d"] as const).map((m) => <button key={m} className={mode === m ? "on" : ""} aria-pressed={mode === m} onClick={() => setMode(m)}>{m.toUpperCase()}</button>)}
        </div>
        <div className="seg col"><button aria-label="Acercar" onClick={() => baseMap.current?.zoomBy(1)}>+</button><button aria-label="Alejar" onClick={() => baseMap.current?.zoomBy(-1)}>−</button></div>
      </div>
      <section className="sidebar">
        <header><h1>Chile</h1><span>Sistema Eléctrico Nacional</span></header>
        <div className="tabs" role="tablist">
          {TABS.map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{label}</button>)}
        </div>
        <div className="tab-body">
          {error && <p className="note warn">{error}</p>}
          {tab === "red" && network && <NetworkPanel network={network} buses={buses} frame={frame} node={node} line={cut} clearNode={() => setNode(null)} cutLine={(id) => { setNode(null); setCut(id); }} />}
          {tab === "sim" && <>
            <p className="muted">Haz clic en una línea del mapa para cortarla y mira cómo se propaga la falla. Haz clic en una subestación para ver su detalle en Red.</p>
            {cut && network && <button className="reset" onClick={() => setCut(null)}>Volver al caso base</button>}
            {timeline && network && <Results timeline={timeline} network={network} events={visibleEvents} cut={cut} now={frame?.t ?? 0} />}
          </>}
          {tab === "legend" && network && <CascadeLegend network={network} buses={buses} mode={mode} />}
          {tab === "assumptions" && <ul className="assumptions">{(timeline?.assumptions ?? index?.assumptions ?? []).map((a) => <li key={a}>{a}</li>)}</ul>}
        </div>
        <TimelineCard timeline={timeline} stage={stage} playing={playing} setPlaying={setPlaying} setStage={(n) => { setPlaying(false); setStage(n); }} />
      </section>
    </div>
  );
}

function Icon({ d, fill = false }: { d: string; fill?: boolean }) {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill={fill ? "currentColor" : "none"} stroke={fill ? "none" : "currentColor"} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d={d} /></svg>;
}

/** Bottom card of the panel (design: play, scrubber, time). It steps through the cascade stages. */
function TimelineCard(p: { timeline: Timeline | null; stage: number; playing: boolean; setPlaying(b: boolean): void; setStage(n: number): void }) {
  const last = (p.timeline?.frames.length ?? 1) - 1;
  const now = Math.min(p.stage, last);
  const seconds = p.timeline?.frames[now]?.t ?? 0;
  return (
    <div className="timeline">
      <div className="timeline-top"><span>{p.timeline?.label ?? ""}</span><b>{seconds.toFixed(1).replace(".", ",")} s</b></div>
      <div className="timeline-row">
        <button className="play" aria-label={p.playing ? "Pausa" : "Reproducir"} disabled={last === 0} onClick={() => p.setPlaying(!p.playing)}>{p.playing ? "❚❚" : "▶"}</button>
        <input type="range" aria-label="Etapa de la cascada" min={0} max={last} value={now} onChange={(e) => p.setStage(Number(e.target.value))} disabled={last === 0} />
        <span className="stage">{now} / {last}</span>
      </div>
    </div>
  );
}

function Results(p: { timeline: Timeline; network: Network; events: Timeline["events"]; cut: string | null; now: number }) {
  const s = p.timeline.summary;
  const pct = s.load_total_mw ? Math.round((s.load_shed_mw / s.load_total_mw) * 100) : 0;
  return (
    <section className="results">
      <h2>{p.cut ? `Corte: ${lineName(p.network, p.cut)}` : "Caso base (sin corte)"}</h2>
      <div className="stats">
        <div><b>{formatPeople(s.people_without_power)}</b><span>personas sin luz</span></div>
        <div><b>{s.load_shed_mw.toLocaleString("es-CL")} MW</b><span>{pct}% de la demanda</span></div>
        <div><b>{s.stages}</b><span>etapas de cascada</span></div>
      </div>
      {p.timeline.truncated && <p className="note warn">La cascada llegó al tope de 20 etapas.</p>}
      <ol className="events">{p.events.map((e, i) => <li key={i}><span className="t">{e.t.toFixed(1)} s</span> {narrate(e, p.network)}</li>)}</ol>
      <FrequencyChart curves={p.timeline.frequency_hz} events={p.timeline.events} now={p.now} />
    </section>
  );
}

