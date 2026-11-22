import type { Layer, PickingInfo } from "@deck.gl/core";
import { useEffect, useMemo, useRef, useState } from "react";
import { createBaseMap, type BaseMap, type ViewMode } from "../map/baseMap";
import { buildRegionalLayers, loadRegionalGrid, regionalFromDocuments, regionalTooltip, type RegionalGrid } from "../map/regional";
import { loadBuses, loadIndex, loadNetwork, loadTimeline } from "./api";
import { interpretClick, NO_CLICK, pickOf, type Pick } from "./clicks";
import { buildCascadeLayers, type ColorMode, type Toggles } from "./layers";
import { GridSources, type SourceSelection } from "./GridSources";
import { composeGrid, loadContextDocument } from "./gridsApi";
import { HelpPanel, SourcesPanel } from "./Legend";
import { MapLegend } from "./MapLegend";
import { MapOverlays, type LocatedMarker } from "./MapOverlays";
import { NetworkPanel } from "./NetworkPanel";
import { ScenarioTree, type ScenarioChoice } from "./Scenarios";
import { SelectionCard } from "./SelectionCard";
import { SimulationPanel } from "./SimulationPanel";
import { darkAt, eventLocation, frameAt, frameIndexAt, frequencyAt, groupEvents, impactAt, type Marker } from "./simulation";
import { clock, formatPeople, lineName, pct, placeName, zoneName } from "./text";
import { stateOf, TimelineCard, TRACK_W, type MarkerState } from "./Timeline";
import type { BusState, Index, Network, Timeline } from "./types";
import { Icon, TipLayer, Wordmark } from "./ui";
import { DataPanel } from "../session/DataPanel";
import { SessionBar } from "../session/SessionBar";
import { SessionCut } from "../session/SessionCut";
import { cutLines, repairLines } from "../session/sessionApi";
import { useSession } from "../session/useSession";
import "./cascade.css";
import "../session/session.css";

type Tab = "red" | "sim" | "datos";
type View = "tabs" | "sources" | "help" | "session";
const TABS: [Tab | "avoid" | "validation", string][] = [["red", "Red"], ["sim", "Simulación"], ["avoid", "Qué lo habría evitado"], ["validation", "Validación"]];
// In a session the two placeholder tabs are left out so Datos fits the 440 px panel.
const SESSION_TABS: [Tab, string][] = [["red", "Red"], ["sim", "Simulación"], ["datos", "Datos"]];
const SOON = "Todavía no está en la app: el motor aún no calcula esta vista.";
const PINNED = "En una sesión el punto está fijo; corta y repara líneas en el mapa y en Simulación.";
const FLOW_PERIOD_S = 3.0;
const FLOW_CYCLE = 1 + 2 / 3;

/**
 * Mapa 3 in the Design v5 shell: click selects, double click cuts a line, and the cascade computed by the engine plays.
 * Without a session it reads web/public/cache and never calls /api; with ?sesion=<sid> the network, the cut and the
 * timeline come from the sessions API (docs/mapa3.md section 11).
 */
export function CascadeApp() {
  const mapRef = useRef<HTMLDivElement>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const scaleRef = useRef<HTMLDivElement>(null);
  const baseMap = useRef<BaseMap | null>(null);
  const params = useMemo(() => new URLSearchParams(location.search), []); // ?point=<id>&cut=<line id>&vista=3d&sesion=<sid>
  const s = useSession();
  const startCut = s.sid ? null : params.get("cut"); // a session owns its cut
  const [index, setIndex] = useState<Index | null>(null);
  const [pointId, setPointId] = useState(params.get("point") ?? "nov2026-1300");
  const [network, setNetwork] = useState<Network | null>(null);
  const [buses, setBuses] = useState<Record<string, BusState>>({});
  // The loaded timeline with the point and cut it belongs to, so a stale one is never shown under a new cut's name.
  const [loaded, setLoaded] = useState<{ key: string; timeline: Timeline } | null>(null);
  const [cut, setCut] = useState<string | null>(startCut);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [tab, setTab] = useState<Tab>(startCut ? "sim" : "red");
  const [view, setView] = useState<View>("tabs");
  const [colorMode, setColorMode] = useState<ColorMode>(startCut ? "load" : "voltage");
  const [selection, setSelection] = useState<Pick | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [mode, setMode] = useState<ViewMode>(params.get("vista") === "3d" ? "3d" : "2d");
  const [toggles, setToggles] = useState<Toggles>({ flow: true, demand: false });
  const [layersOpen, setLayersOpen] = useState(false);
  const [hasLabels, setHasLabels] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  // The grid composed by the backend from the documents picked in "Fuentes de la grilla"; null: the app cache.
  const [composed, setComposed] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);
  const sourcesRef = useRef<SourceSelection>({ chile: true, context: [] }); // ticked in Fuentes de la grilla, kept for the rail's scenarios
  const pickRef = useRef<((lon: number, lat: number) => void) | null>(null); // map pick mode of the Datos tab

  const point = index?.points.find((p) => p.id === pointId);
  const timeline = loaded?.timeline ?? null;
  // In a session the timeline is the session state's, keyed "session".
  const timelineReady = loaded?.key === (s.sid ? "session" : `${pointId}/${cut ?? "baseline"}`);
  const cuts = s.sid ? s.state?.open_lines ?? [] : cut ? [cut] : [];
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
  const regionalLayers = useMemo<Layer[]>(() => (regional ? buildRegionalLayers(regional, colorMode) : []), [regional, colorMode]);

  const hasCascade = cuts.length > 0 && !!timeline && timelineReady && timeline.events.length > 1;
  const live = useRef({ network, buses, frame, colorMode, selection, mode, toggles, playing, speed, duration, t, regionalLayers, layersOpen, hasCascade, cutLine });
  live.current = { network, buses, frame, colorMode, selection, mode, toggles, playing, speed, duration, t, regionalLayers, layersOpen, hasCascade, cutLine };
  const prevSid = useRef(s.sid);
  const clickMemory = useRef(NO_CLICK);
  const controlsRef = useRef<HTMLDivElement>(null);
  const panelBodyRef = useRef<HTMLDivElement>(null);
  const timelineRequest = useRef("");

  useEffect(() => { loadIndex().then(setIndex).catch((e) => setError(String(e.message))); }, []);
  useEffect(() => { loadRegionalGrid().then(setRegional).catch((e) => console.error("No se pudo cargar la red regional", e)); }, []);
  useEffect(() => { if (!s.sid && !composed) _loadPoint(); }, [pointId, index, s.sid, composed]);
  useEffect(() => { if (!s.sid) _loadTimeline(); }, [pointId, cut, network, s.sid]);
  useEffect(() => { if (s.network) { setNetwork(s.network); setBuses(s.network.buses); setPointId(s.network.point); } }, [s.network]);
  useEffect(() => { if (s.state) { timelineRequest.current = "session"; setLoaded({ key: "session", timeline: s.state.timeline }); setT(0); setPlaying(s.state.open_lines.length > 0); } }, [s.state]);
  useEffect(() => _onSessionChange(), [s.sid]);
  useEffect(() => _mountMap(), []);
  useEffect(() => { baseMap.current?.setMode(mode); }, [mode]);
  useEffect(() => _animate(), []);
  useEffect(() => { _syncUrl(); }, [pointId, cut, mode, s.sid]);
  useEffect(() => _keyboard(), []);
  // A new selection opens at the top of the panel, so bring the top back into view if the panel was scrolled.
  useEffect(() => { if (selection) panelBodyRef.current?.scrollTo({ top: 0 }); }, [selection]);
  useEffect(() => {
    if (!layersOpen) return;
    const close = (e: PointerEvent) => { if (!controlsRef.current?.contains(e.target as Node)) setLayersOpen(false); };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [layersOpen]);

  function _loadPoint() {
    if (!index?.points.some((p) => p.id === pointId)) return;
    const info = index.points.find((p) => p.id === pointId)!;
    Promise.all([loadNetwork(info.year), loadBuses(pointId)]).then(([n, b]) => {
      setNetwork(n); setBuses(b); setError(null);
      // The 2025 and 2026 networks share line and substation ids; drop a selection only if the new network lacks it.
      setSelection((s) => (s && (s.kind === "line" ? n.lines : n.nodes).some((x) => x.id === s.id) ? s : null));
    }).catch((e) => setError(String(e.message)));
  }

  /** Why: the grid on the map is whatever the user picked from the stored documents, not only the app cache. */
  async function composeFromSources(point: string, picked: SourceSelection) {
    setComposing(true);
    sourcesRef.current = picked;
    try {
      const grid = await composeGrid({ point, context: picked.context });
      const docs = await Promise.all(grid.context.map(loadContextDocument));
      setNetwork(picked.chile ? grid.network : { nodes: [], lines: [] }); setBuses(picked.chile ? grid.operating : {});
      setRegional(regionalFromDocuments(docs));
      setError(null); setSelection(null);
      if (!picked.chile) { setCut(null); setLoaded(null); setTab("red"); }
      setComposed(`${picked.chile ? grid.label : "sin Chile"}, ${docs.length} ${docs.length === 1 ? "país" : "países"} de contexto`);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setComposing(false);
    }
  }
  function backToCache() {
    setComposed(null);
    loadRegionalGrid().then(setRegional).catch(() => setRegional(null));
  }

  function _loadTimeline() {
    if (!network) return;
    const key = `${pointId}/${cut ?? "baseline"}`;
    timelineRequest.current = key;
    loadTimeline(pointId, cut ?? "baseline").then((tl) => {
      if (timelineRequest.current !== key) return; // a newer point or cut was asked for meanwhile
      setLoaded({ key, timeline: tl }); setT(0); setPlaying(!!cut);
    }).catch((e) => {
      if (timelineRequest.current !== key) return;
      if (!cut) return setError(String(e.message));
      // A cut kept across a change of hour can lack its file at the new point: fall back to the base case and say so.
      setNotice(`No hay simulación de este corte para ${index?.points.find((x) => x.id === pointId)?.label ?? pointId}. Se muestra el caso base.`);
      setCut(null);
    });
  }

  /** Entering a session from its view opens Datos; leaving one drops the cut and the session-only tab. */
  function _onSessionChange() {
    const was = prevSid.current;
    prevSid.current = s.sid;
    if (!was && s.sid && view === "session") { setView("tabs"); setTab("datos"); setColorMode("voltage"); }
    else if (was && !s.sid) { setCut(null); setLoaded(null); setTab((x) => (x === "datos" ? "red" : x)); }
  }
  function _syncUrl() {
    const q = new URLSearchParams(location.search);
    q.set("point", pointId);
    if (cut && !s.sid) q.set("cut", cut); else q.delete("cut");
    if (mode === "3d") q.set("vista", "3d"); else q.delete("vista");
    history.replaceState(null, "", `${location.pathname}?${q}`);
  }

  function _mountMap() {
    const map = createBaseMap(mapRef.current!, {
      onClick: (info: PickingInfo, tapCount: number) => {
        if (pickRef.current && info.coordinate) {
          pickRef.current(info.coordinate[0], info.coordinate[1]);
          pickRef.current = null;
          setPicking(false);
          return;
        }
        const { action, memory } = interpretClick(pickOf(info.layer?.id ?? "", info.object), tapCount, performance.now(), clickMemory.current);
        clickMemory.current = memory;
        if (action.type === "select") select(action.target);
        else if (action.type === "cut") live.current.cutLine(action.id);
        else if (action.type === "clear") setSelection(null);
      },
      getTooltip: (info: PickingInfo) => _tooltip(info),
      isClickable: (info: PickingInfo) => pickOf(info.layer?.id ?? "", info.object) != null,
    }, live.current.mode);
    baseMap.current = map;
    setHasLabels(map.hasLabels);
    map.setMode(live.current.mode);
    return () => map.dispose();
  }

  function _tooltip(info: PickingInfo) {
    const { network: net, frame: f, buses: b } = live.current;
    if (!info.object || !net) return null;
    // deck.gl puts the tooltip at the pointer and lets it run off the map: place it beside the pointer and flip it near the right and bottom edges.
    const box = mapRef.current;
    const flipX = info.x > (box?.clientWidth ?? Infinity) - 340, flipY = info.y > (box?.clientHeight ?? Infinity) - 120;
    const transform = `translate(${flipX ? `calc(${info.x - 12}px - 100%)` : `${info.x + 12}px`}, ${flipY ? `calc(${info.y - 12}px - 100%)` : `${info.y + 12}px`})`;
    const style = { background: "#1E1F21F7", color: "#E6E6E8", border: "1px solid #FFFFFF1A", borderRadius: "0", padding: "8px 10px", font: "12px/16px var(--font-sans)", whiteSpace: "pre-line", fontVariantNumeric: "tabular-nums", maxWidth: "320px", transform };
    const layer = info.layer?.id ?? "";
    if (layer.startsWith("regional-")) return { text: regionalTooltip(layer, info.object) ?? "", style };
    if (layer.startsWith("lines")) {
      const obj = info.object as { id?: string; line?: { id: string } };
      const id = obj.line?.id ?? obj.id!;
      const e = f?.edges[id];
      const state = e?.status === "open" ? "fuera de servicio" : e ? `${Math.abs(e.flow_mw).toLocaleString("es-CL")} MW · ${pct(e.loading)} de su capacidad` : "sin flujo calculado";
      // A line that is already out of service cannot be taken out again: only offer its detail.
      return { text: `${lineName(net, id)}\n${state}\n${e?.status === "open" ? "Clic: detalle" : "Clic: detalle · doble clic: sacar de servicio"}`, style };
    }
    const n = info.object as { id: string; name: string; kv: number; zone: string };
    const bus = b[n.id];
    const dark = f?.dark.includes(n.id);
    return { text: `${placeName(n.name)}\n${Math.round(n.kv)} kV · ${zoneName(n.zone)}${bus ? `\n${Math.round(bus.load_mw).toLocaleString("es-CL")} MW de demanda · ${formatPeople(bus.people)} personas` : ""}${dark ? "\nSin suministro" : ""}\nClic: detalle`, style };
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
        const sel = v.selection;
        map.setLayers(buildCascadeLayers({ network: v.network, buses: v.buses, frame: v.frame, time, colorMode: v.colorMode, selectedNode: sel?.kind === "node" ? sel.id : null,
          selectedLine: sel?.kind === "line" ? sel.id : null, mode: v.mode, zoom, toggles: v.toggles, regional: v.regionalLayers }));
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

  /** Space plays or pauses (not while a control has focus); Escape closes the layers popover, else clears the selection. */
  function _keyboard() {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const inControl = !!el?.closest?.("input, select, textarea, button, [contenteditable]");
      if (e.key === "Escape") {
        if (live.current.layersOpen) setLayersOpen(false);
        else setSelection(null);
      } else if (e.key === " " && !inControl && live.current.hasCascade) {
        e.preventDefault();
        togglePlay();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }

  /** Selecting never switches tabs or the line colour; it only leaves Ayuda or Fuentes for the tabs. */
  function select(target: Pick) {
    setSelection(target);
    setView("tabs");
  }

  /** Without a session the cut is local; in a session the line opens for everyone through `POST /{sid}/cut`. */
  function cutLine(id: string) {
    setSelection(null); // the impact card names the cut and stays at the top of the panel
    setNotice(null);
    if (!s.sid) setCut(id);
    else if (!s.state?.open_lines.includes(id)) s.edit((sid, rev) => cutLines(sid, [id], rev));
    setView("tabs");
    setTab("sim");
    setColorMode("load");
  }

  /**
   * Back to the base case at the same operating point; the tab and the selection stay. In a session it repairs `lines`
   * (every open line when omitted) for everyone through `POST /{sid}/repair`.
   */
  function restore(lines?: string[]) {
    setNotice(null);
    if (!s.sid) setCut(null);
    else s.edit((sid, rev) => repairLines(sid, lines ? { lines } : { all: true }, rev));
  }

  function togglePlay() {
    const v = live.current;
    if (v.duration > 0 && v.t >= v.duration - 1e-6) { seek(0); setPlaying(true); } else setPlaying(!v.playing);
  }

  function chooseTab(next: Tab) {
    setView("tabs");
    setTab(next);
    setColorMode(next === "sim" ? "load" : "voltage");
  }

  function seek(time: number) {
    live.current.t = time;
    setT(time);
  }

  function _pick(onPoint: (lon: number, lat: number) => void) {
    pickRef.current = onPoint;
    setPicking(true);
  }
  function openScenario(next: ScenarioChoice) {
    setSelection(null);
    setNotice(null);
    setPointId(next.point);
    setCut(next.cut);
    if (composed) void composeFromSources(next.point, sourcesRef.current); // the composed grid follows the chosen hour
    chooseTab("sim");
  }

  const tabs: [Tab | "avoid" | "validation", string][] = s.sid ? SESSION_TABS : TABS;
  // In a session the selected line is "cut" when it is open, and restoring it repairs that line alone.
  const selectedCut = s.sid ? (selection?.kind === "line" && cuts.includes(selection.id) ? selection.id : null) : cut;
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
        <ScenarioTree points={index?.points ?? []} pointId={pointId} cuts={cuts} network={network} open={openScenario} locked={s.sid ? PINNED : undefined} />
        <button className="rail-item" aria-disabled="true" data-tip={SOON}><Icon><path d="M3 8.5l3 3 7-7" /></Icon><span>Validación</span></button>
        <button className={view === "sources" ? "rail-item on" : "rail-item"} onClick={() => setView(view === "sources" ? "tabs" : "sources")}>
          <Icon><ellipse cx="8" cy="4" rx="5.5" ry="2" /><path d="M2.5 4v8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2V4M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2" /></Icon><span>Fuentes y supuestos</span>
        </button>
        <GridSources composed={composed} busy={composing} apply={(picked) => void composeFromSources(pointId, picked)} reset={backToCache} locked={!!s.sid} />
        <button className={view === "session" ? "rail-item on" : "rail-item"} onClick={() => setView(view === "session" ? "tabs" : "session")}>
          <Icon><path d="M6.5 9.5l3-3M7.2 4.3l1.1-1.1a2.6 2.6 0 0 1 3.7 3.7l-1.1 1.1M8.8 11.7l-1.1 1.1a2.6 2.6 0 0 1-3.7-3.7l1.1-1.1" /></Icon><span>Sesión compartida</span>
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
              {s.sid && <SessionBar s={s} compact />}
              <div className="tabs" role="tablist">
                {tabs.map(([k, label]) => {
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
              <h1>{view === "sources" ? "Fuentes y supuestos" : view === "session" ? "Sesión compartida" : "Ayuda"}</h1>
              <button className="text-btn" onClick={() => setView("tabs")}>Cerrar</button>
            </div>
          )}
        </header>
        <div className="panel-body" ref={panelBodyRef}>
          {(s.error ?? error) && <p className="note">{s.error ?? error}{s.error && <> <button className="text-btn" onClick={s.clearError}>Cerrar</button></>}</p>}
          {view === "session" && <SessionBar s={s} />}
          {notice && <div className="notice" role="status"><span>{notice}</span><button className="text-btn" onClick={() => setNotice(null)}>Cerrar</button></div>}
          {view === "sources" && <SourcesPanel assumptions={timeline?.assumptions ?? index?.assumptions ?? []} index={index} />}
          {view === "help" && network && <HelpPanel network={network} buses={buses} mode={mode} regional={regional} />}
          {view === "tabs" && !network && !error && <Loading text="Cargando la red" />}
          {view === "tabs" && network && selection && (
            <SelectionCard network={network} buses={buses} frame={frame} selection={selection} cut={selectedCut} year={point?.year}
              select={select} clear={() => setSelection(null)} cutLine={cutLine} restore={() => restore(selectedCut && s.sid ? [selectedCut] : undefined)} />
          )}
          {view === "tabs" && tab === "red" && network && <NetworkPanel source={sourceNote} />}
          {view === "tabs" && tab === "sim" && s.sid && s.state && network && (
            <SessionCut network={network} open={s.state.open_lines} notice={s.state.notice} repair={(lines) => restore(lines)} />
          )}
          {view === "tabs" && tab === "sim" && network && (timeline && timelineReady ? (
            <SimulationPanel network={network} timeline={timeline} cuts={cuts} t={t} impact={impact} islands={islands} totalPeople={totalPeople}
              seek={seek} openSources={() => setView("sources")} restore={() => restore()} source={sourceNote} />
          ) : !error && <Loading text="Cargando la simulación" />)}
          {view === "tabs" && tab === "datos" && (s.network
            ? <DataPanel network={s.network} edit={s.edit} pick={_pick} picking={picking} />
            : <p className="meta">Cargando la sesión…</p>)}
        </div>
      </section>

      <TimelineCard timeline={cuts.length && timelineReady ? timeline : null} loading={cuts.length > 0 && !timelineReady} markers={markers} t={t} clock={clock(point?.snapshot, t).tenths} islands={cuts.length ? islands : []} playing={playing} speed={speed}
        setPlaying={setPlaying} togglePlay={togglePlay} seek={(x) => { setPlaying(false); seek(x); }} setSpeed={setSpeed} />

      <div className="map-controls" ref={controlsRef}>
        <button className={layersOpen ? "ctl on" : "ctl"} aria-label="Capas y vista" aria-expanded={layersOpen} onClick={() => setLayersOpen(!layersOpen)}>
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden><path d="M8 2L1.5 5.5 8 9l6.5-3.5zM1.5 8.5L8 12l6.5-3.5M1.5 11.3L8 14.8l6.5-3.5" fill="none" stroke="#E6E6E8" strokeWidth="1.2" strokeLinejoin="round" /></svg>
        </button>
        <div className="ctl-stack">
          <button className="ctl" aria-label="Acercar" onClick={() => baseMap.current?.zoomBy(1)}><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M7 2v10M2 7h10" stroke="#E6E6E8" strokeWidth="1.4" strokeLinecap="round" /></svg></button>
          <button className="ctl" aria-label="Alejar" onClick={() => baseMap.current?.zoomBy(-1)}><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M2 7h10" stroke="#E6E6E8" strokeWidth="1.4" strokeLinecap="round" /></svg></button>
        </div>
        <button className="ctl" aria-label="Ver todo Chile" data-tip="Ver todo Chile" onClick={() => baseMap.current?.fitAll()}>
          <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M1.5 5V1.5H5M9 1.5h3.5V5M12.5 9v3.5H9M5 12.5H1.5V9" fill="none" stroke="#E6E6E8" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" /></svg>
        </button>
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

const Loading = ({ text }: { text: string }) => <div className="card loading" role="status" aria-live="polite"><span className="loading-bar" /><p>{text}</p></div>;

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
