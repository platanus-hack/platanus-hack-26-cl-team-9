import type { Layer, PickingInfo } from "@deck.gl/core";
import { useEffect, useMemo, useRef, useState } from "react";
import { createBaseMap, type BaseMap, type ViewMode } from "../map/baseMap";
import { buildRegionalLayers, loadRegionalGrid, regionalTooltip, type RegionalGrid } from "../map/regional";
import { loadBuses, loadIndex, loadNetwork, loadTimeline } from "./api";
import { buildCascadeLayers, type ColorMode, type Toggles } from "./layers";
import { HelpPanel, SourcesPanel } from "./Legend";
import { MapLegend } from "./MapLegend";
import { MapOverlays, type LocatedMarker } from "./MapOverlays";
import { NetworkPanel } from "./NetworkPanel";
import { ScenarioTree, type ScenarioChoice } from "./Scenarios";
import { SimulationPanel } from "./SimulationPanel";
import { darkAt, eventLocation, frameAt, frameIndexAt, frequencyAt, groupEvents, impactAt, type Marker } from "./simulation";
import { clock, formatPeople, lineName, pct, placeName, zoneName } from "./text";
import { stateOf, TimelineCard, TRACK_W, type MarkerState } from "./Timeline";
import type { BusState, Index, Network, Timeline } from "./types";
import { Icon, TipLayer, Wordmark } from "./ui";
import "./cascade.css";

type Tab = "red" | "sim";
type View = "tabs" | "sources" | "help";
const TABS: [Tab | "avoid" | "validation", string][] = [["red", "Red"], ["sim", "Simulación"], ["avoid", "Qué lo habría evitado"], ["validation", "Validación"]];
const SOON = "Todavía no está en la app: el motor aún no calcula esta vista.";
const FLOW_PERIOD_S = 3.0;
const FLOW_CYCLE = 1 + 2 / 3;

/** Mapa 3 in the Design v5 shell: click a line to cut it and watch the cascade computed by the engine (web/public/cache). */
export function CascadeApp() {
  const mapRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const scaleRef = useRef<HTMLDivElement>(null);
  const baseMap = useRef<BaseMap | null>(null);
  const params = useMemo(() => new URLSearchParams(location.search), []); // ?point=<id>&cut=<line id>&vista=3d
  const [index, setIndex] = useState<Index | null>(null);
  const [pointId, setPointId] = useState(params.get("point") ?? "nov2026-1300");
  const [network, setNetwork] = useState<Network | null>(null);
  const [buses, setBuses] = useState<Record<string, BusState>>({});
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [cut, setCut] = useState<string | null>(params.get("cut"));
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [tab, setTab] = useState<Tab>(params.get("cut") ? "sim" : "red");
  const [view, setView] = useState<View>("tabs");
  const [colorMode, setColorMode] = useState<ColorMode>(params.get("cut") ? "load" : "voltage");
  const [node, setNode] = useState<string | null>(null);
  const [mode, setMode] = useState<ViewMode>(params.get("vista") === "3d" ? "3d" : "2d");
  const [toggles, setToggles] = useState<Toggles>({ flow: true, demand: false });
  const [layersOpen, setLayersOpen] = useState(false);
  const [hasLabels, setHasLabels] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const point = index?.points.find((p) => p.id === pointId);
  const duration = timeline?.duration_s ?? 0;
  const fi = timeline ? frameIndexAt(timeline, t) : 0;
  const darkCount = timeline ? darkAt(timeline, t).size : 0;
  const frame = useMemo(() => (timeline ? frameAt(timeline, t) : undefined), [timeline, fi, darkCount]);
  const impact = useMemo(() => (timeline ? impactAt(timeline, buses, t) : { people: 0, lostLoadMw: 0, lostGenMw: 0, share: 0 }), [timeline, buses, t]);
  const islands = useMemo(() => (timeline ? frequencyAt(timeline, t) : []), [timeline, t]);
  const totalPeople = useMemo(() => Object.values(buses).reduce((s, b) => s + b.people, 0), [buses]);
  const markers = useMemo(() => (timeline && timeline.events.length > 1 ? groupEvents(timeline.events, timeline.duration_s, TRACK_W) : []), [timeline]);
  const located = useMemo(() => (timeline && network ? locate(markers, timeline, network) : []), [markers, timeline, network]);
  const visible = timeline?.events.filter((e) => e.t <= t + 1e-9).length ?? 0;
  const states = useMemo(() => new Map<Marker, MarkerState>(markers.map((m) => [m, stateOf(m, visible)])), [markers, visible]);
  // On the map the highlighted pin is the latest event that has a place, even when the latest event overall has none.
  const mapStates = useMemo(() => {
    const out = new Map<Marker, MarkerState>();
    const shown = located.filter((l) => states.get(l.marker) !== "future");
    located.forEach((l) => out.set(l.marker, states.get(l.marker) === "future" ? "future" : l === shown[shown.length - 1] ? "current" : "past"));
    return out;
  }, [located, states]);

  const [regional, setRegional] = useState<RegionalGrid | null>(null);
  const regionalLayers = useMemo<Layer[]>(() => (regional ? buildRegionalLayers(regional) : []), [regional]);

  const live = useRef({ network, buses, frame, colorMode, node, mode, toggles, playing, speed, duration, t, regionalLayers });
  live.current = { network, buses, frame, colorMode, node, mode, toggles, playing, speed, duration, t, regionalLayers };

  useEffect(() => { loadIndex().then(setIndex).catch((e) => setError(String(e.message))); }, []);
  useEffect(() => { loadRegionalGrid().then(setRegional).catch((e) => console.error("No se pudo cargar la red regional", e)); }, []);
  useEffect(() => { _loadPoint(); }, [pointId, index]);
  useEffect(() => { _loadTimeline(); }, [pointId, cut, network]);
  useEffect(() => _mountMap(), []);
  useEffect(() => { baseMap.current?.setMode(mode); }, [mode]);
  useEffect(() => _animate(), []);
  useEffect(() => { _syncUrl(); }, [pointId, cut, mode]);

  function _loadPoint() {
    if (!index?.points.some((p) => p.id === pointId)) return;
    const info = index.points.find((p) => p.id === pointId)!;
    Promise.all([loadNetwork(info.year), loadBuses(pointId)]).then(([n, b]) => { setNetwork(n); setBuses(b); setError(null); }).catch((e) => setError(String(e.message)));
  }

  function _loadTimeline() {
    if (!network) return;
    loadTimeline(pointId, cut ?? "baseline").then((tl) => { setTimeline(tl); setT(0); setPlaying(!!cut); }).catch((e) => setError(String(e.message)));
  }

  function _syncUrl() {
    const q = new URLSearchParams(location.search);
    q.set("point", pointId);
    if (cut) q.set("cut", cut); else q.delete("cut");
    if (mode === "3d") q.set("vista", "3d"); else q.delete("vista");
    history.replaceState(null, "", `${location.pathname}?${q}`);
  }

  function _mountMap() {
    const map = createBaseMap(mapRef.current!, {
      onClick: (info: PickingInfo) => {
        const obj = info.object as { id?: string; line?: { id: string } } | undefined;
        const id = obj?.line?.id ?? obj?.id;
        if (!id) return;
        const layer = info.layer?.id ?? "";
        if (layer.startsWith("lines")) cutLine(id);
        else if (layer === "nodes" || layer === "load" || layer === "load-2d") { setNode(id); setView("tabs"); setTab("red"); }
      },
      getTooltip: (info: PickingInfo) => _tooltip(info),
    }, live.current.mode);
    baseMap.current = map;
    setHasLabels(map.hasLabels);
    map.setMode(live.current.mode);
    return () => map.dispose();
  }

  function _tooltip(info: PickingInfo) {
    const { network: net, frame: f, buses: b } = live.current;
    if (!info.object || !net) return null;
    const style = { background: "#1E1F21F7", color: "#E6E6E8", border: "1px solid #FFFFFF1A", borderRadius: "0", padding: "8px 10px", font: "12px/16px var(--font-sans)", whiteSpace: "pre-line", fontVariantNumeric: "tabular-nums" };
    const layer = info.layer?.id ?? "";
    if (layer.startsWith("regional-")) return { text: regionalTooltip(layer, info.object) ?? "", style };
    if (layer.startsWith("lines")) {
      const obj = info.object as { id?: string; line?: { id: string } };
      const id = obj.line?.id ?? obj.id!;
      const e = f?.edges[id];
      const state = e?.status === "open" ? "fuera de servicio" : e ? `${Math.abs(e.flow_mw).toLocaleString("es-CL")} MW · ${pct(e.loading)} de su capacidad` : "sin flujo calculado";
      return { text: `${lineName(net, id)}\n${state}\nClic para sacarla de servicio`, style };
    }
    const n = info.object as { id: string; name: string; kv: number; zone: string };
    const bus = b[n.id];
    const dark = f?.dark.includes(n.id);
    return { text: `${placeName(n.name)}\n${Math.round(n.kv)} kV · ${zoneName(n.zone)}${bus ? `\n${Math.round(bus.load_mw).toLocaleString("es-CL")} MW de demanda · ${formatPeople(bus.people)} personas` : ""}${dark ? "\nSin suministro" : ""}`, style };
  }

  /** One loop moves the simulation clock, redraws the deck.gl layers and moves the HTML overlays with the camera. */
  function _animate() {
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const v = live.current;
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      if (v.playing && v.duration > 0) {
        const next = Math.min(v.duration, v.t + dt * v.speed);
        live.current.t = next;
        setT(next);
        if (next >= v.duration) setPlaying(false);
      }
      const map = baseMap.current;
      if (map && v.network && v.frame) {
        const time = ((now / 1000) / FLOW_PERIOD_S) % FLOW_CYCLE;
        const zoom = map.camera().zoom;
        map.setLayers(buildCascadeLayers({ network: v.network, buses: v.buses, frame: v.frame, time, colorMode: v.colorMode, selectedNode: v.node, mode: v.mode, zoom, toggles: v.toggles, regional: v.regionalLayers }));
        _placeOverlays(map);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }

  function _placeOverlays(map: BaseMap) {
    const root = overlayRef.current;
    if (root) {
      const width = root.clientWidth;
      const height = root.clientHeight;
      root.querySelectorAll<HTMLElement>("[data-lon]").forEach((el) => {
        const [x, y] = map.project(Number(el.dataset.lon), Number(el.dataset.lat));
        el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
        el.classList.toggle("flip", x > width - 340);
        el.classList.toggle("up", y > height - 300);
      });
      // The first event keeps a short label, unless it would sit under the current event's callout.
      const label = root.querySelector<HTMLElement>(".pin-label");
      const callout = root.querySelector<HTMLElement>(".callout");
      if (label) {
        label.style.visibility = "";
        if (callout) {
          const a = label.getBoundingClientRect(), b = callout.getBoundingClientRect();
          const overlap = a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom;
          label.style.visibility = overlap ? "hidden" : "";
        }
      }
    }
    const scale = scaleRef.current;
    if (scale) {
      const { lat, zoom } = map.camera();
      const metersPerPx = (40075016.686 * Math.cos((lat * Math.PI) / 180)) / (512 * 2 ** zoom);
      const km = [1, 2, 5, 10, 20, 50, 100, 200, 300, 500, 1000].filter((k) => (k * 1000) / metersPerPx <= 110).pop() ?? 1;
      (scale.firstElementChild as HTMLElement).style.width = `${((km * 1000) / metersPerPx).toFixed(0)}px`;
      (scale.lastElementChild as HTMLElement).textContent = `${km.toLocaleString("es-CL")} km`;
    }
  }

  function cutLine(id: string) {
    setNode(null);
    setCut(id);
    setView("tabs");
    setTab("sim");
    setColorMode("load");
  }

  function chooseTab(next: Tab) {
    setView("tabs");
    setTab(next);
    setColorMode(next === "red" ? "voltage" : "load");
  }

  function seek(time: number) {
    live.current.t = time;
    setT(time);
  }

  function openScenario(next: ScenarioChoice) {
    setNode(null);
    setPointId(next.point);
    setCut(next.cut);
    chooseTab("sim");
  }

  const sourceNote = hasLabels ? "Mapa base: Mapbox" : "Contorno: data/processed/chile.geojson";

  return (
    <div className="shell">
      <div className="map" ref={mapRef} />
      <div className="map-overlays" ref={overlayRef}>
        {network && <MapOverlays markers={located} states={mapStates} visible={visible} network={network} impact={impact} showCities={!hasLabels} select={seek} />}
      </div>

      <nav className="rail" aria-label="Navegación">
        <Wordmark />
        <button className="rail-item on" aria-current="page" onClick={() => setView("tabs")}>
          <Icon><path d="M1.5 3.5l4-1.5 5 2 4-1.5v10l-4 1.5-5-2-4 1.5z M5.5 2v10 M10.5 4v10" /></Icon><span>Mapa</span>
        </button>
        <div className="rail-item static"><Icon><path d="M2 13.5h12M4 11V7M8 11V3M12 11V8" /></Icon><span>Escenarios</span></div>
        <ScenarioTree points={index?.points ?? []} pointId={pointId} cut={cut} network={network} open={openScenario} />
        <button className="rail-item" aria-disabled="true" data-tip={SOON}><Icon><path d="M3 8.5l3 3 7-7" /></Icon><span>Validación</span></button>
        <button className={view === "sources" ? "rail-item on" : "rail-item"} onClick={() => setView(view === "sources" ? "tabs" : "sources")}>
          <Icon><ellipse cx="8" cy="4" rx="5.5" ry="2" /><path d="M2.5 4v8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2V4M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2" /></Icon><span>Fuentes y supuestos</span>
        </button>
        <div className="rail-spacer" />
        <button className={view === "help" ? "rail-item faint on" : "rail-item faint"} onClick={() => setView(view === "help" ? "tabs" : "help")}>
          <Icon><circle cx="8" cy="8" r="5.8" /><path d="M6.3 6.3a1.8 1.8 0 1 1 2.4 1.7c-.5.2-.7.6-.7 1.1M8 11.3v.1" /></Icon><span>Ayuda</span>
        </button>
      </nav>

      <section className="panel" aria-label="Panel">
        <header className="panel-head">
          {view === "tabs" ? (
            <>
              <div className="crumbs"><h1>Chile</h1><span>Sistema Eléctrico Nacional</span></div>
              <div className="tabs" role="tablist">
                {TABS.map(([k, label]) => {
                  const soon = k === "avoid" || k === "validation";
                  return (
                    <button key={k} role="tab" aria-selected={tab === k} aria-disabled={soon || undefined} className={tab === k ? "on" : ""}
                      data-tip={soon ? SOON : undefined} onClick={() => !soon && chooseTab(k as Tab)}>{label}</button>
                  );
                })}
              </div>
            </>
          ) : (
            <div className="crumbs view-head">
              <h1>{view === "sources" ? "Fuentes y supuestos" : "Ayuda"}</h1>
              <button className="text-btn" onClick={() => setView("tabs")}>Cerrar</button>
            </div>
          )}
        </header>
        <div className="panel-body">
          {error && <p className="note">{error}</p>}
          {view === "sources" && <SourcesPanel assumptions={timeline?.assumptions ?? index?.assumptions ?? []} index={index} />}
          {view === "help" && network && <HelpPanel network={network} buses={buses} mode={mode} regional={regional} />}
          {view === "tabs" && tab === "red" && network && (
            <NetworkPanel network={network} buses={buses} frame={frame} node={node} clearNode={() => setNode(null)} cutLine={cutLine} source={sourceNote} />
          )}
          {view === "tabs" && tab === "sim" && network && timeline && (
            <SimulationPanel network={network} timeline={timeline} cut={cut} t={t} impact={impact} islands={islands} totalPeople={totalPeople}
              seek={seek} openSources={() => setView("sources")} source={sourceNote} />
          )}
        </div>
      </section>

      <TimelineCard timeline={cut ? timeline : null} markers={markers} t={t} clock={clock(point?.snapshot, t).tenths} islands={cut ? islands : []} playing={playing} speed={speed}
        setPlaying={setPlaying} seek={(x) => { setPlaying(false); seek(x); }} setSpeed={setSpeed} />

      <div className="map-controls">
        <button className={layersOpen ? "ctl on" : "ctl"} aria-label="Capas y vista" aria-expanded={layersOpen} onClick={() => setLayersOpen(!layersOpen)}>
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden><path d="M8 2L1.5 5.5 8 9l6.5-3.5zM1.5 8.5L8 12l6.5-3.5M1.5 11.3L8 14.8l6.5-3.5" fill="none" stroke="#E6E6E8" strokeWidth="1.2" strokeLinejoin="round" /></svg>
        </button>
        <div className="ctl-stack">
          <button className="ctl" aria-label="Acercar" onClick={() => baseMap.current?.zoomBy(1)}><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M7 2v10M2 7h10" stroke="#E6E6E8" strokeWidth="1.4" strokeLinecap="round" /></svg></button>
          <button className="ctl" aria-label="Alejar" onClick={() => baseMap.current?.zoomBy(-1)}><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M2 7h10" stroke="#E6E6E8" strokeWidth="1.4" strokeLinecap="round" /></svg></button>
        </div>
        {layersOpen && (
          <div className="layers-pop" role="dialog" aria-label="Capas">
            <h3>Vista</h3>
            <div className="seg" role="group" aria-label="Vista del mapa">
              {(["2d", "3d"] as const).map((m) => <button key={m} className={mode === m ? "on" : ""} aria-pressed={mode === m} onClick={() => setMode(m)}>{m.toUpperCase()}</button>)}
            </div>
            <h3>Capas</h3>
            <label className="check"><input type="checkbox" checked={toggles.flow} onChange={(e) => setToggles({ ...toggles, flow: e.target.checked })} />Flujo de potencia</label>
            <label className="check"><input type="checkbox" checked={toggles.demand} onChange={(e) => setToggles({ ...toggles, demand: e.target.checked })} />Demanda por subestación</label>
          </div>
        )}
      </div>

      <div className="map-foot">
        <div className="scale" ref={scaleRef}><span className="scale-bar" /><span className="scale-label" /></div>
        {network && <MapLegend mode={colorMode} setMode={setColorMode} network={network} frame={frame} />}
      </div>
      <TipLayer />
    </div>
  );
}

/** Map position of each timeline marker: its first event that has a place (lines, shed zone, dark area). */
function locate(markers: Marker[], tl: Timeline, network: Network): LocatedMarker[] {
  const out: LocatedMarker[] = [];
  for (const marker of markers) {
    for (const e of marker.events) {
      const loc = eventLocation(e, tl, network);
      if (!loc) continue;
      const zone = e.type === "load_shed" ? zoneName(String(e.params.zone)) : e.type === "island_blackout" ? majorityZone(e.t, tl, network) : "";
      out.push({ marker, lon: loc[0], lat: loc[1], zone });
      break;
    }
  }
  return out;
}

function majorityZone(t: number, tl: Timeline, network: Network): string {
  const before = darkAt(tl, t - 1e-3);
  const count = new Map<string, number>();
  for (const id of darkAt(tl, t)) if (!before.has(id)) { const z = network.nodes.find((n) => n.id === id)?.zone ?? ""; count.set(z, (count.get(z) ?? 0) + 1); }
  const top = [...count.entries()].sort((a, b) => b[1] - a[1])[0];
  return top ? zoneName(top[0]) : "";
}
