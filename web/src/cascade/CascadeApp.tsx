import type { Layer, PickingInfo } from "@deck.gl/core";
import { useEffect, useMemo, useRef, useState } from "react";
import { createBaseMap, type BaseMap, type ViewMode } from "../map/baseMap";
import { BUILT_IN, DEFAULT_COUNTRY, isUpload, networkFromParam, UPLOAD_PREFIX, VIEW_ONLY, type NetworkInfo } from "../map/country";
import { cameraTarget, type LonLat } from "../map/countryBounds";
import { countryName } from "../map/iso3";
import { buildRegionalLayers, loadCountryGrid, loadOutline, regionalCountries, regionalFromDocuments, regionalTooltip, type RegionalGrid } from "../map/regional";
import { deleteUpload, listUploads, newUploadId, saveUpload, type StoredNetwork } from "../map/uploadStore";
import { loadBuses, loadHealth, loadIndex, loadNetwork, loadTimeline } from "./api";
import { interpretClick, NO_CLICK, pickOf, type Pick } from "./clicks";
import { buildCascadeLayers, type ColorMode, type Toggles } from "./layers";
import { GridSources } from "./GridSources";
import { addBus, addLine, dropBus, dropLine, editKey, fromCache, loadEdits, NO_EDITS, saveEdits, type Edits } from "./edits";
import { composeGrid, loadContextDocument, loadDependency, simulateGrid, type SimulationResult } from "./gridsApi";
import { HEAT_OPTIONS, heatLayers, heatPoints, needsDependency, type HeatKind } from "./heat";
import { HelpPanel, SourcesPanel } from "./Legend";
import { MapLegend } from "./MapLegend";
import { MapOverlays, type LocatedMarker } from "./MapOverlays";
import { NetworkPanel, type Origin } from "./NetworkPanel";
import { NetworkPicker } from "./NetworkPicker";
import { summaryFromGrid, summaryFromManifest } from "./networkSummary";
import { NetworkState } from "./NetworkState";
import { ScenarioTree, type ScenarioChoice } from "./Scenarios";
import { SelectionCard } from "./SelectionCard";
import { SimulationPanel } from "./SimulationPanel";
import { UploadNetwork, type UploadedNetwork } from "./UploadNetwork";
import { darkAt, eventLocation, frameAt, frameIndexAt, frequencyAt, groupEvents, impactAt, type Marker } from "./simulation";
import { clock, formatPeople, lineName, pct, placeName, shutdownNode, substationLines, zoneName } from "./text";
import { stateOf, TimelineCard, TRACK_W, type MarkerState } from "./Timeline";
import type { BusState, DependencyNode, HealthReport, Index, Network, Timeline } from "./types";
import { Icon, TipLayer, Wordmark } from "./ui";
import { DataPanel } from "../session/DataPanel";
import { SessionBar } from "../session/SessionBar";
import { SessionCut } from "../session/SessionCut";
import { cutLines, repairLines } from "../session/sessionApi";
import { canPowerAll, powerAll } from "./powerAll";
import { useSession } from "../session/useSession";
import { AssistantPanel } from "../assistant/AssistantPanel";
import { useAssistant } from "../assistant/useAssistant";
import { IncidentPanel } from "../incidents/IncidentPanel";
import { useIncident } from "../incidents/useIncident";
import { DEFAULT_POINT, syncedSearch } from "./url";
import "./cascade.css";
import "../session/session.css";

type Tab = "estado" | "red" | "sim" | "datos";
type View = "tabs" | "sources" | "help" | "session" | "assistant" | "incidents" | "upload";
// "Qué lo habría evitado" and "Validación" are not built yet and left out so the four tabs fit the 440 px panel.
const TABS: [Tab, string][] = [["estado", "Estado de la red"], ["red", "Red"], ["sim", "Simulación"]];
// In a session Datos replaces Estado de la red: the session owns its changes.
const SESSION_TABS: [Tab, string][] = [["red", "Red"], ["sim", "Simulación"], ["datos", "Datos"]];
const SOON = "Todavía no está en la app: el motor aún no calcula esta vista.";
const PINNED = "En una sesión el punto está fijo; corta y repara líneas en el mapa y en Simulación.";
const SESSION_NETWORK = "Una sesión compartida usa la red de Chile.";
// Networks shipped with the build: Chile plus every country whose drawn layer exists (docs/regional.md).
const AVAILABLE: NetworkInfo[] = BUILT_IN.filter((n) => n.id === DEFAULT_COUNTRY || regionalCountries.includes(n.id));
// Tabs that need the engine: only Chile's network can be simulated (issue #49).
const SIM_TABS = new Set<Tab>(["estado", "sim"]);
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
  // ?point=<id>&cut=<line id | sub-<bus id>>&vista=3d&sesion=<sid>; the URL carries only values that differ from the defaults (url.ts)
  const params = useMemo(() => new URLSearchParams(location.search), []);
  const s = useSession();
  const a = useAssistant(s); // owned here so the chat survives view changes
  const inc = useIncident(s); // likewise for the incident result and the cascade it plays
  // ?pais=<ISO3> opens that country's network; a session is always Chile's (its API is Chile-only).
  const startNetwork = s.sid ? DEFAULT_COUNTRY : networkFromParam(params.get("pais"), AVAILABLE.map((n) => n.id));
  const startCut = s.sid || startNetwork !== DEFAULT_COUNTRY ? null : params.get("cut"); // a session owns its cut
  const [index, setIndex] = useState<Index | null>(null);
  const [pointId, setPointId] = useState(params.get("point") ?? DEFAULT_POINT);
  const [network, setNetwork] = useState<Network | null>(null);
  const [buses, setBuses] = useState<Record<string, BusState>>({});
  const [health, setHealth] = useState<HealthReport | null>(null);
  // The loaded timeline with the point and cut it belongs to, so a stale one is never shown under a new cut's name.
  const [loaded, setLoaded] = useState<{ key: string; timeline: Timeline } | null>(null);
  // Every change the user made outside a session, kept together (docs/grids.md); a session owns its own cuts.
  // A link's cut wins; otherwise the changes saved in this browser come back (a refresh never loses them).
  const [edits, setEdits] = useState<Edits>(() => (s.sid ? NO_EDITS : !startCut ? loadEdits() : shutdownNode(startCut) ? addBus(NO_EDITS, shutdownNode(startCut)!) : addLine(NO_EDITS, startCut)));
  const [simResult, setSimResult] = useState<SimulationResult | null>(null);
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [tab, setTab] = useState<Tab>(startCut ? "sim" : "red");
  const [view, setView] = useState<View>("tabs");
  // Desastres (a cut) open on Carga, Benchmark (no cut) on Tensión, also when the rail picks them (chooseTab).
  const [colorMode, setColorMode] = useState<ColorMode>(startCut ? "load" : "voltage");
  const [selection, setSelection] = useState<Pick | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [mode, setMode] = useState<ViewMode>(params.get("vista") === "3d" ? "3d" : "2d");
  const [toggles, setToggles] = useState<Toggles>({ flow: true, demand: false });
  const [layersOpen, setLayersOpen] = useState(false);
  const [heat, setHeat] = useState<HeatKind>("none");
  // Heat-map data from POST /grids/dependency for the grid as it stands, keyed so a late answer never shows under newer changes.
  const [dependency, setDependency] = useState<{ key: string; nodes: Record<string, DependencyNode> } | null>(null);
  const [heatError, setHeatError] = useState<string | null>(null);
  const [hasLabels, setHasLabels] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  // The grid composed by the backend from the documents picked in "Fuentes de la grilla"; null: the app cache.
  const [composed, setComposed] = useState<string | null>(null);
  const [composing, setComposing] = useState(false);
  const pickRef = useRef<((lon: number, lat: number) => void) | null>(null); // map pick mode of the Datos tab
  // One network on the map at a time (issue #49): Chile's (simulated) or a view-only one, built in, composed or uploaded.
  const [networkId, setNetworkId] = useState(startNetwork);
  const [uploads, setUploads] = useState<StoredNetwork[]>([]);
  const [shown, setShown] = useState<{ id: string; grid: RegionalGrid; from: "file" | "composed" } | null>(null);
  const networks = useMemo<NetworkInfo[]>(() => [...AVAILABLE, ...uploads.map((u) => (
    { id: `${UPLOAD_PREFIX}${u.id}`, country: u.country, name: u.name, system: `Red subida · ${countryName(u.country)}`, simulable: false, uploaded: true }
  ))], [uploads]);
  const current = networks.find((n) => n.id === networkId) ?? AVAILABLE[0];
  const isChile = networkId === DEFAULT_COUNTRY;
  const shownGrid = !isChile && shown?.id === networkId ? shown.grid : null;

  const point = index?.points.find((p) => p.id === pointId);
  // An incident cycle's cascade (its snapshot `transient`, a Timeline) plays over the session's own timeline.
  const incidentTl = inc.playing != null ? inc.cascadeAt(inc.playing) : null;
  const timeline = incidentTl ?? loaded?.timeline ?? null;
  // In a session the timeline is the session state's, keyed "session".
  const cached = fromCache(edits); // zero or one line: the precalculated cascade; more changes: the server simulates them together
  const cut = cached ? edits.lines[0] ?? null : null;
  const timelineKey = s.sid ? "session" : cached ? `${pointId}/${cut ?? "baseline"}` : editKey(pointId, edits);
  const timelineReady = !!incidentTl || loaded?.key === timelineKey;
  const cuts = s.sid ? s.state?.open_lines ?? [] : edits.lines;
  const outBuses = s.sid ? [] : edits.buses;
  const edited = !!incidentTl || cuts.length + outBuses.length > 0;
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

  const heatKey = `${pointId}|${[...cuts].sort()}|${[...outBuses].sort()}`;
  const heatData = dependency?.key === heatKey ? dependency.nodes : null;
  const heatLayerList = useMemo<Layer[]>(() => (network ? heatLayers(heat, heatPoints(heat, network, buses, heatData)) : []), [heat, network, buses, heatData]);
  const regionalLayers = useMemo<Layer[]>(() => (shownGrid ? buildRegionalLayers(shownGrid, colorMode) : []), [shownGrid, colorMode]);

  const hasCascade = edited && !!timeline && timelineReady && timeline.events.length > 1;
  const live = useRef({ network, buses, frame, colorMode, selection, mode, toggles, playing, speed, duration, t, regionalLayers, heatLayerList, heatKey, layersOpen, hasCascade, cutLine, outBus, isChile });
  live.current = { network, buses, frame, colorMode, selection, mode, toggles, playing, speed, duration, t, regionalLayers, heatLayerList, heatKey, layersOpen, hasCascade, cutLine, outBus, isChile };
  const fitted = useRef<string | null>(null); // the network the camera last flew to
  const prevSid = useRef(s.sid);
  const clickMemory = useRef(NO_CLICK);
  const controlsRef = useRef<HTMLDivElement>(null);
  const panelBodyRef = useRef<HTMLDivElement>(null);
  const timelineRequest = useRef("");
  const incidentOn = useRef(false); // an incident cascade is on the map

  useEffect(() => { loadIndex().then(setIndex).catch((e) => setError(String(e.message))); }, []);
  // Only Chile by default; another network replaces it on the map when picked in the header or in Fuentes de la grilla.
  useEffect(() => { listUploads().then(setUploads).catch(() => { /* no local storage: uploads last for the visit */ }); }, []);
  useEffect(() => { if (s.sid && networkId !== DEFAULT_COUNTRY) chooseNetwork(DEFAULT_COUNTRY); }, [s.sid]);
  useEffect(() => _loadShown(), [networkId, uploads]);
  useEffect(() => _fitNetwork(), [networkId, network, shownGrid]);
  useEffect(() => { if (!s.sid) saveEdits(edits); }, [edits, s.sid]);
  useEffect(() => _loadHeat(), [heat, heatKey]);
  useEffect(() => { if (!s.sid && !composed) _loadPoint(); }, [pointId, index, s.sid, composed]);
  useEffect(() => { if (!s.sid) _loadTimeline(); }, [pointId, edits, network, s.sid]);
  // Pre-fault health of the base point; null when the cache predates it. Hidden in a session or a composed grid: they change the network.
  useEffect(() => { let live = true; setHealth(null); loadHealth(pointId).then((h) => { if (live) setHealth(h); }); return () => { live = false; }; }, [pointId]);
  useEffect(() => { if (s.network) { setNetwork(s.network); setBuses(s.network.buses); setPointId(s.network.point); } }, [s.network]);
  useEffect(() => { if (s.state) { timelineRequest.current = "session"; setLoaded({ key: "session", timeline: s.state.timeline }); setT(0); setPlaying(s.state.open_lines.length > 0); } }, [s.state]);
  useEffect(() => _onSessionChange(), [s.sid]);
  // Choosing an incident cycle plays its cascade from 0; leaving it goes back to the session's timeline, paused at 0.
  useEffect(() => {
    if (incidentTl) { incidentOn.current = true; seek(0); setPlaying(true); setColorMode("load"); }
    else if (incidentOn.current) { incidentOn.current = false; seek(0); setPlaying(false); }
  }, [incidentTl]);
  useEffect(() => _mountMap(), []);
  useEffect(() => { baseMap.current?.setMode(mode); }, [mode]);
  useEffect(() => _animate(), []);
  useEffect(() => { _syncUrl(); }, [pointId, edits, mode, s.sid, networkId]);
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

  /**
   * Why: the network on the map can come from the documents the backend stores, not only from the app files. One network
   * at a time (issue #49): Chile is composed with no context; another country is composed from its context document alone.
   */
  async function composeFromSources(point: string, country: string, key: string | null) {
    setComposing(true);
    try {
      const chile = country === DEFAULT_COUNTRY;
      const grid = await composeGrid({ point, context: chile || !key ? [] : [key] });
      const docs = await Promise.all(grid.context.map(loadContextDocument));
      setError(null); setSelection(null);
      if (chile) { setNetwork(grid.network); setBuses(grid.operating); } else setShown({ id: country, grid: regionalFromDocuments(docs), from: "composed" });
      setComposed(country);
      _showNetwork(country);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setComposing(false);
    }
  }
  /** Back to the app files: Chile from the cache, other countries from data/processed/latam. */
  function backToCache() {
    setComposed(null);
    setShown((x) => (x?.from === "composed" ? null : x));
  }

  /** The view-only network: an uploaded one is in memory, a built-in country is fetched once (regional.ts), a composed one is kept. */
  function _loadShown() {
    if (networkId === DEFAULT_COUNTRY || shown?.id === networkId) return;
    if (isUpload(networkId)) {
      const u = uploads.find((x) => `${UPLOAD_PREFIX}${x.id}` === networkId);
      if (u) setShown({ id: networkId, grid: u.grid, from: "file" });
      return;
    }
    let stale = false;
    loadCountryGrid(networkId).then((grid) => { if (!stale) setShown({ id: networkId, grid, from: "file" }); })
      .catch((e) => { if (!stale) setError(`No se pudo cargar la red de ${current.name}: ${e.message}`); });
    return () => { stale = true; };
  }

  /**
   * Flies to the network once it is loaded: the frame comes from its buses, the limits from its country's outline
   * (countryBounds.ts). The first fit (page load, `?pais=`) jumps; later ones fly. Uploads get no land check: their
   * country is only declared.
   */
  function _fitNetwork() {
    const map = baseMap.current;
    if (!map || fitted.current === networkId) return;
    const buses: LonLat[] | null = networkId === DEFAULT_COUNTRY ? network?.nodes.map((n) => [n.lon, n.lat] as LonLat) ?? null : shownGrid?.substations.map((x) => x.position) ?? null;
    if (!buses?.length) return;
    const first = fitted.current === null;
    const key = networkId;
    fitted.current = key;
    (isUpload(key) ? Promise.resolve(null) : loadOutline(current.country)).then((outline) => {
      const target = cameraTarget(buses, outline);
      if (target && fitted.current === key) map.setTarget(target, first ? 0 : undefined);
    });
  }

  /** Shows another network: the previous one leaves the map. Chile's changes stay; they come back with Chile. */
  function _showNetwork(id: string) {
    setNetworkId(id);
    setSelection(null);
    setNotice(null);
    setView("tabs");
    if (id !== DEFAULT_COUNTRY) { setPlaying(false); setTab("red"); setColorMode("voltage"); }
  }
  /** The header picks from the app files and uploads, so it leaves a composed grid. */
  function chooseNetwork(id: string) {
    if (composed) backToCache();
    _showNetwork(id);
  }

  function addUpload(n: UploadedNetwork) {
    const stored: StoredNetwork = { id: newUploadId(), name: n.name, country: n.country, grid: n.grid, savedAt: new Date().toISOString() };
    const id = `${UPLOAD_PREFIX}${stored.id}`;
    setUploads((u) => [...u, stored]);
    setShown({ id, grid: stored.grid, from: "file" });
    chooseNetwork(id);
    saveUpload(stored).catch(() => setNotice("La red se muestra, pero este navegador no permitió guardarla: se perderá al recargar la página."));
  }

  function removeUpload(id: string) {
    const raw = id.slice(UPLOAD_PREFIX.length);
    setUploads((u) => u.filter((x) => x.id !== raw));
    if (networkId === id) chooseNetwork(DEFAULT_COUNTRY);
    deleteUpload(raw).catch(() => { /* not stored: nothing to delete */ });
  }

  function _loadTimeline() {
    if (!network) return;
    timelineRequest.current = timelineKey;
    const key = timelineKey;
    if (!cached) return _simulateEdits(key);
    setSimResult(null);
    loadTimeline(pointId, cut ?? "baseline").then((tl) => {
      if (timelineRequest.current !== key) return; // a newer point or cut was asked for meanwhile
      setLoaded({ key, timeline: tl }); setT(0); setPlaying(!!cut);
    }).catch((e) => {
      if (timelineRequest.current !== key) return;
      if (!cut) return setError(String(e.message));
      // A cut kept across a change of hour can lack its file at the new point: fall back to the base case and say so.
      setNotice(`No hay simulación de este corte para ${index?.points.find((x) => x.id === pointId)?.label ?? pointId}. Se muestra el caso base.`);
      setEdits(NO_EDITS);
    });
  }

  /** Dependency and criticality come from the server, computed on the grid after the changes and their cascade. */
  function _loadHeat() {
    setHeatError(null);
    if (!needsDependency(heat) || dependency?.key === heatKey) return;
    const key = heatKey;
    loadDependency({ point: pointId, open_lines: cuts, out_buses: outBuses })
      .then((r) => { if (live.current.heatKey === key) setDependency({ key, nodes: r.nodes }); })
      .catch((e) => { if (live.current.heatKey === key) setHeatError(String(e.message)); });
  }

  /** Why: the cache has single cuts only; two or more changes are simulated together by the backend. */
  function _simulateEdits(key: string) {
    simulateGrid({ point: pointId, open_lines: edits.lines, out_buses: edits.buses }).then((r) => {
      if (timelineRequest.current !== key) return;
      setError(null); setSimResult(r); setLoaded({ key, timeline: r.timeline }); setT(0); setPlaying(true);
    }).catch((e) => {
      if (timelineRequest.current !== key) return;
      setError(`${String(e.message)} Repón un cambio en Estado de la red.`);
    });
  }

  /** Entering a session from its view opens Datos; leaving one drops the cut and the session-only tab. */
  function _onSessionChange() {
    const was = prevSid.current;
    prevSid.current = s.sid;
    if (!was && s.sid && view === "session") { setView("tabs"); setTab("datos"); setColorMode("voltage"); }
    else if (was && !s.sid) { setEdits(NO_EDITS); setLoaded(null); setTab((x) => (x === "datos" ? "red" : x)); }
  }
  function _syncUrl() {
    // Another country's network is view only: its URL names the country and carries no cut.
    const country = isUpload(networkId) ? DEFAULT_COUNTRY : networkId;
    const search = syncedSearch(location.search, { pointId, cut: country === DEFAULT_COUNTRY ? cut : null, mode, sid: s.sid, country });
    history.replaceState(null, "", location.pathname + search + location.hash);
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
        else if (action.type === "cut") (action.kind === "line" ? live.current.cutLine : live.current.outBus)(action.id);
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
    if (!info.object) return null;
    // deck.gl puts the tooltip at the pointer and lets it run off the map: place it beside the pointer and flip it near the right and bottom edges.
    const box = mapRef.current;
    const flipX = info.x > (box?.clientWidth ?? Infinity) - 340, flipY = info.y > (box?.clientHeight ?? Infinity) - 120;
    const transform = `translate(${flipX ? `calc(${info.x - 12}px - 100%)` : `${info.x + 12}px`}, ${flipY ? `calc(${info.y - 12}px - 100%)` : `${info.y + 12}px`})`;
    const style = { background: "#1E1F21F7", color: "#E6E6E8", border: "1px solid #FFFFFF1A", borderRadius: "0", padding: "8px 10px", font: "12px/16px var(--font-sans)", whiteSpace: "pre-line", fontVariantNumeric: "tabular-nums", maxWidth: "320px", transform };
    const layer = info.layer?.id ?? "";
    // `text`, never `html`: names from an uploaded file are shown as typed, not interpreted.
    if (layer.startsWith("regional-")) return { text: regionalTooltip(layer, info.object) ?? "", style };
    if (!net) return null;
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
    let drawn: Layer[] | null = null; // a view-only network's layers do not animate: set them only when they change
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
      if (map && !v.isChile) {
        if (drawn !== v.regionalLayers) { map.setLayers(v.regionalLayers); drawn = v.regionalLayers; }
        _placeOverlays(map);
      } else if (map && v.network && v.frame) {
        drawn = null;
        const time = ((now / 1000) / FLOW_PERIOD_S) % FLOW_CYCLE;
        const zoom = map.camera().zoom;
        const sel = v.selection;
        map.setLayers(buildCascadeLayers({ network: v.network, buses: v.buses, frame: v.frame, time, colorMode: v.colorMode, selectedNode: sel?.kind === "node" ? sel.id : null,
          selectedLine: sel?.kind === "line" ? sel.id : null, mode: v.mode, zoom, toggles: v.toggles, heat: v.heatLayerList }));
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

  /** Without a session the cut adds to the list of changes; in a session the line opens for everyone through `POST /{sid}/cut`. */
  function cutLine(id: string) {
    setSelection(null); // the impact card names the cut and stays at the top of the panel
    setNotice(null);
    inc.stop();
    if (!s.sid) setEdits((e) => addLine(e, id));
    else if (!s.state?.open_lines.includes(id)) s.edit((sid, rev) => cutLines(sid, [id], rev));
    setView("tabs");
    setTab("sim");
    setColorMode("load");
  }

  /**
   * Shutting down a substation is one more change on the list (out of service with its load and generation). In a session
   * its lines that are still closed open for everyone through `POST /{sid}/cut`.
   */
  function outBus(id: string) {
    setSelection(null);
    setNotice(null);
    inc.stop();
    if (!s.sid) setEdits((e) => addBus(e, id));
    else if (network) {
      const closed = substationLines(network, id).filter((l) => !s.state?.open_lines.includes(l));
      if (closed.length) s.edit((sid, rev) => cutLines(sid, closed, rev));
    }
    setView("tabs");
    setTab("sim");
    setColorMode("load");
  }

  /**
   * Back to the base case at the same operating point; the tab and the selection stay. With `lines` only those are put back
   * (every change when omitted). In a session it repairs them for everyone through `POST /{sid}/repair`.
   */
  function restore(lines?: string[]) {
    setNotice(null);
    if (!s.sid) setEdits((e) => (lines ? lines.reduce(dropLine, e) : NO_EDITS));
    else s.edit((sid, rev) => repairLines(sid, lines ? { lines } : { all: true }, rev));
  }
  function restoreBus(id: string) { setEdits((e) => dropBus(e, id)); }
  /** "Encender subestación": puts that substation back; in a session it repairs its lines. */
  function powerOn(id: string) {
    if (!s.sid) restoreBus(id);
    else if (network) restore(substationLines(network, id));
  }

  /**
   * "Prender todo": back to the full network at the same point. Clears the cut, the selection and the notice, and puts the
   * timeline at 0 paused; the tab, the colour mode and the view stay. In a session it repairs every open line for everyone
   * after a confirmation; session dataset edits stay ("Restablecer" in Datos drops them).
   */
  function powerAllOn() {
    if (inc.playing != null) { // the incident cascade leaves the map first; open session lines still need a repair
      inc.stop();
      seek(0);
      setPlaying(false);
      if (!cuts.length) return;
    }
    if (s.sid) {
      if (!confirm("¿Prender toda la red? Repara todas las líneas abiertas para todos los participantes de la sesión.")) return;
      restore();
      setSelection(null);
      seek(0);
      setPlaying(false);
      return;
    }
    const next = powerAll({ pointId, cut, selection, t: live.current.t, playing: live.current.playing });
    setEdits(NO_EDITS); // every change goes, lines and substations
    setSelection(next.selection);
    seek(next.t);
    setPlaying(next.playing);
    setNotice(null);
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
    if (!current.simulable) return;
    setSelection(null);
    setNotice(null);
    setPointId(next.point);
    if (next.edits) setEdits(next.edits); // a disaster replaces the changes; a Benchmark condition keeps them
    if (composed === DEFAULT_COUNTRY) void composeFromSources(next.point, DEFAULT_COUNTRY, null); // the composed grid follows the chosen hour
    chooseTab(next.edits ? "sim" : "red"); // a disaster opens on Simulación (Carga), a Benchmark condition on Red (Tensión)
  }

  const tabs: [Tab, string][] = s.sid ? SESSION_TABS : TABS;
  // In a session the selected line is "cut" when it is open, and restoring it repairs that line alone.
  const selectedCut = selection?.kind === "line" && cuts.includes(selection.id) ? selection.id : null;
  const canPower = canPowerAll({ cuts, edited: outBuses.length > 0 || inc.playing != null });
  const shutDown = selection?.kind === "node" && (s.sid
    ? !!network && substationLines(network, selection.id).length > 0 && substationLines(network, selection.id).every((l) => cuts.includes(l))
    : edits.buses.includes(selection.id));
  const sourceNote = hasLabels ? "Mapa base: Mapbox" : isChile ? "Contorno: data/processed/chile.geojson" : "Contornos: data/processed/latam/outlines.geojson (geoBoundaries)";
  const shownSummary = shownGrid ? (shownGrid.countries[0] ? summaryFromManifest(shownGrid.countries[0]) : summaryFromGrid(shownGrid)) : null;
  const shownOrigin = shownGrid ? originOf(current, shownGrid) : undefined;

  return (
    <div className="shell">
      <div className="map" ref={mapRef} />
      <div className="map-overlays" ref={overlayRef}>
        {isChile && network && <MapOverlays markers={located} states={mapStates} visible={visible} network={network} impact={impact} showCities={!hasLabels} select={seek} />}
      </div>

      <nav className="rail" aria-label="Navegación">
        <Wordmark />
        <button className="rail-item on" aria-current="page" onClick={() => setView("tabs")}>
          <Icon><path d="M1.5 3.5l4-1.5 5 2 4-1.5v10l-4 1.5-5-2-4 1.5z M5.5 2v10 M10.5 4v10" /></Icon><span>Mapa</span>
        </button>
        <div className="rail-item static"><Icon><path d="M2 13.5h12M4 11V7M8 11V3M12 11V8" /></Icon><span>Escenarios</span></div>
        <ScenarioTree points={index?.points ?? []} pointId={pointId} edits={s.sid ? { lines: cuts, buses: [] } : edits} open={openScenario} locked={s.sid ? PINNED : !current.simulable ? VIEW_ONLY : undefined} />
        <button className="rail-item" aria-disabled="true" data-tip={SOON}><Icon><path d="M3 8.5l3 3 7-7" /></Icon><span>Validación</span></button>
        <button className={view === "sources" ? "rail-item on" : "rail-item"} onClick={() => setView(view === "sources" ? "tabs" : "sources")}>
          <Icon><ellipse cx="8" cy="4" rx="5.5" ry="2" /><path d="M2.5 4v8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2V4M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2" /></Icon><span>Fuentes y supuestos</span>
        </button>
        <GridSources current={networkId} composed={composed} busy={composing} apply={(country, key) => void composeFromSources(pointId, country, key)} reset={backToCache} locked={!!s.sid} />
        <button className={view === "session" ? "rail-item on" : "rail-item"} onClick={() => setView(view === "session" ? "tabs" : "session")}>
          <Icon><path d="M6.5 9.5l3-3M7.2 4.3l1.1-1.1a2.6 2.6 0 0 1 3.7 3.7l-1.1 1.1M8.8 11.7l-1.1 1.1a2.6 2.6 0 0 1-3.7-3.7l1.1-1.1" /></Icon><span>Sesión compartida</span>
        </button>
        <button className={view === "assistant" ? "rail-item on" : "rail-item"} onClick={() => setView(view === "assistant" ? "tabs" : "assistant")}>
          <Icon><path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z M5.5 7h.01M8 7h.01M10.5 7h.01" /></Icon><span>Asistente</span>
        </button>
        <button className={view === "incidents" ? "rail-item on" : "rail-item"} onClick={() => setView(view === "incidents" ? "tabs" : "incidents")}>
          <Icon><path d="M8 1.8l6.2 11.2H1.8z M8 6.2v3.3M8 11.3v.1" /></Icon><span>Incidentes</span>
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
              <NetworkPicker current={current} networks={networks} choose={chooseNetwork} remove={removeUpload} upload={() => setView("upload")} locked={s.sid ? SESSION_NETWORK : undefined} />
              {s.sid && <SessionBar s={s} compact />}
              <div className="tabs" role="tablist">
                {tabs.map(([k, label]) => {
                  const viewOnly = !current.simulable && SIM_TABS.has(k);
                  return (
                    <button key={k} role="tab" aria-selected={tab === k} aria-disabled={viewOnly || undefined} className={tab === k ? "on" : ""}
                      data-tip={viewOnly ? VIEW_ONLY : undefined} onClick={() => !viewOnly && chooseTab(k)}>{label}</button>
                  );
                })}
              </div>
            </>
          ) : (
            <div className="crumbs view-head">
              <h1>{VIEW_TITLES[view] ?? "Ayuda"}</h1>
              <button className="text-btn" onClick={() => setView("tabs")}>Cerrar</button>
            </div>
          )}
        </header>
        <div className="panel-body" ref={panelBodyRef}>
          {(s.error ?? error) && <p className="note">{s.error ?? error}{s.error && <> <button className="text-btn" onClick={s.clearError}>Cerrar</button></>}</p>}
          {view === "session" && <SessionBar s={s} />}
          {view === "assistant" && <AssistantPanel a={a} />}
          {view === "incidents" && <IncidentPanel inc={inc} sessionPoint={s.sid ? s.session?.point ?? null : null} />}
          {notice && <div className="notice" role="status"><span>{notice}</span><button className="text-btn" onClick={() => setNotice(null)}>Cerrar</button></div>}
          {view === "sources" && <SourcesPanel assumptions={timeline?.assumptions ?? index?.assumptions ?? []} index={index} />}
          {view === "help" && network && <HelpPanel network={network} buses={buses} mode={mode} regional={shownGrid} />}
          {view === "upload" && <UploadNetwork add={addUpload} cancel={() => setView("tabs")} />}
          {view === "tabs" && !(isChile ? network : shownGrid) && !error && <Loading text="Cargando la red" />}
          {view === "tabs" && !isChile && tab === "red" && shownGrid && (
            <NetworkPanel source={sourceNote} summary={shownSummary} origin={shownOrigin} viewOnly={VIEW_ONLY} />
          )}
          {view === "tabs" && isChile && network && selection && (
            <SelectionCard network={network} buses={buses} frame={frame} selection={selection} cut={selectedCut} year={point?.year}
              select={select} clear={() => setSelection(null)} cutLine={cutLine} restore={() => restore(selectedCut ? [selectedCut] : undefined)}
              shutDown={shutDown} shutdown={outBus} powerOn={powerOn} />
          )}
          {view === "tabs" && isChile && tab === "estado" && network && (s.sid
            ? <p className="meta">En una sesión compartida los cambios están en Simulación y Datos.</p>
            : <NetworkState network={network} buses={buses} point={pointId} edits={edits} result={simResult} timeline={timelineReady ? timeline : null} restoreLine={(id) => restore([id])} restoreBus={restoreBus} restoreAll={() => restore()} />)}
          {view === "tabs" && isChile && tab === "red" && network && <NetworkPanel source={sourceNote} />}
          {view === "tabs" && isChile && tab === "sim" && s.sid && s.state && network && (
            <SessionCut network={network} open={s.state.open_lines} notice={s.state.notice} repair={(lines) => restore(lines)} />
          )}
          {view === "tabs" && isChile && tab === "sim" && network && (timeline && timelineReady ? (
            <SimulationPanel network={network} timeline={timeline} cuts={cuts} outBuses={outBuses} t={t} impact={impact} islands={islands} totalPeople={totalPeople}
              seek={seek} openSources={() => setView("sources")} restore={() => restore()} source={sourceNote} health={s.sid || composed ? null : health} />
          ) : !error && <Loading text="Cargando la simulación" />)}
          {view === "tabs" && tab === "datos" && (s.network
            ? <DataPanel network={s.network} edit={s.edit} pick={_pick} picking={picking} />
            : <p className="meta">Cargando la sesión…</p>)}
        </div>
      </section>

      {isChile && <TimelineCard timeline={edited && timelineReady ? timeline : null} loading={edited && !timelineReady} markers={markers} t={t} clock={clock(point?.snapshot, t).tenths} islands={edited ? islands : []} playing={playing} speed={speed}
        setPlaying={setPlaying} togglePlay={togglePlay} seek={(x) => { setPlaying(false); seek(x); }} setSpeed={setSpeed} />}

      {isChile && <button className="power-all" aria-disabled={!canPower || undefined} onClick={() => canPower && powerAllOn()}
        data-tip={!canPower ? "No hay nada apagado ni editado." : s.sid ? "Repara todas las líneas abiertas de la sesión y vuelve al caso base de esta hora." : "Repone lo apagado y vuelve al caso base de esta hora."}>
        <Icon size={14}><path d="M9 1.5L3.5 9H8l-1 5.5L12.5 7H8z" /></Icon><span>Prender todo</span>
      </button>}

      <div className="map-controls" ref={controlsRef}>
        <button className={layersOpen ? "ctl on" : "ctl"} aria-label="Capas y vista" aria-expanded={layersOpen} onClick={() => setLayersOpen(!layersOpen)}>
          <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden><path d="M8 2L1.5 5.5 8 9l6.5-3.5zM1.5 8.5L8 12l6.5-3.5M1.5 11.3L8 14.8l6.5-3.5" fill="none" stroke="#E6E6E8" strokeWidth="1.2" strokeLinejoin="round" /></svg>
        </button>
        <div className="ctl-stack">
          <button className="ctl" aria-label="Acercar" onClick={() => baseMap.current?.zoomBy(1)}><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M7 2v10M2 7h10" stroke="#E6E6E8" strokeWidth="1.4" strokeLinecap="round" /></svg></button>
          <button className="ctl" aria-label="Alejar" onClick={() => baseMap.current?.zoomBy(-1)}><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden><path d="M2 7h10" stroke="#E6E6E8" strokeWidth="1.4" strokeLinecap="round" /></svg></button>
        </div>
        <button className="ctl" aria-label="Ver toda la red" data-tip="Ver toda la red" onClick={() => baseMap.current?.fitAll()}>
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
            <h3>Mapa de calor</h3>
            {HEAT_OPTIONS.map((o) => (
              <label className="check" key={o.kind}><input type="radio" name="heat" checked={heat === o.kind} onChange={() => setHeat(o.kind)} />{o.label}</label>
            ))}
            {heat !== "none" && <p className="heat-hint">{heatError ?? (needsDependency(heat) && !heatData ? "Calculando en el servidor…" : HEAT_OPTIONS.find((o) => o.kind === heat)?.hint)}</p>}
          </div>
        )}
      </div>

      <div className="map-foot">
        <div className="scale" ref={scaleRef}><span className="scale-bar" /><span className="scale-label" /></div>
        {isChile && network && <MapLegend mode={colorMode} setMode={setColorMode} network={network} frame={frame} />}
      </div>
      <TipLayer />
    </div>
  );
}

const VIEW_TITLES: Partial<Record<View, string>> = { sources: "Fuentes y supuestos", session: "Sesión compartida", assistant: "Asistente", incidents: "Incidentes", upload: "Subir una red" };

/** Where a view-only network's figures come from: the manifest's sources for a country, the file for an upload. */
function originOf(n: NetworkInfo, grid: RegionalGrid): Origin {
  const entry = grid.countries[0];
  if (!entry) {
    const what = `de la red subida (${n.name})`;
    return { source: `archivo subido por el usuario, país declarado ${n.country}`, km: `Suma del largo de las líneas ${what}; si una línea no trae length_km se mide su trazo.`,
      substations: `Subestaciones ${what}.`, mw: `Potencia de las centrales ${what}.`, bands: `Largo de las líneas ${what} por nivel de tensión.` };
  }
  const sources = entry.sources.map((x) => x.name).join("; ");
  const reduced = "de la capa reducida (una barra por subestación, líneas paralelas plegadas; docs/regional.md sección 2), en data/processed/latam/manifest.json";
  return { source: `${sources} (data/processed/latam/manifest.json)`, km: `Largo de las líneas ${reduced}. Cuenta el circuito más largo de cada corredor, así que subestima.`,
    substations: `Subestaciones ${reduced}.`, mw: `Potencia instalada de las centrales asignadas a una subestación ${reduced}.`, bands: `Largo de las líneas ${reduced}, por nivel de tensión.` };
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
