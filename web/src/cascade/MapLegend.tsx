import { HEAT_ENDS, HEAT_OPTIONS, heatGradient, type HeatKind } from "./heat";
import { DEAD_LINE, FAULT, LOAD_BANDS, OPEN_LINE, VOLTAGE_TIERS, loadColor, type ColorMode } from "./layers";
import type { Frame, Network } from "./types";
import { TECH_COLORS, TECH_NAMES } from "../map/layers";
import type { RegionalGrid } from "../map/regional";

const MODES: [ColorMode, string][] = [["voltage", "Tensión"], ["load", "Carga"]];

/**
 * Legend card at the bottom right (Design v5). It lists line samples, never a segmented bar. The load legend always
 * shows the same six items; items absent from the current frame keep a 40 % swatch.
 */
export function MapLegend({ mode, setMode, network, frame, cascade = false, justDark = false, heat = null }: {
  mode: ColorMode; setMode(m: ColorMode): void; network: Network; frame: Frame | undefined;
  /** A cut's timeline is on the map: show the ring for substations that just lost supply (`justDark`: one is pulsing now). */
  cascade?: boolean; justDark?: boolean;
  /** The active heat map, so its key stays visible once the layers popover closes (A2-07): pending while the server computes it. */
  heat?: { kind: Exclude<HeatKind, "none">; pending: boolean; error: string | null } | null;
}) {
  return (
    <section className="legend-card" aria-label="Leyenda">
      <div className="legend-head">
        <h3>Color de líneas</h3>
        {/* The existing segmented control instead of a native select (D16, E-15). */}
        <div className="seg legend-seg" role="group" aria-label="Qué indica el color de las líneas">
          {MODES.map(([m, label]) => <button key={m} className={mode === m ? "on" : ""} aria-pressed={mode === m} onClick={() => setMode(m)}>{label}</button>)}
        </div>
      </div>
      {/* "recién sin suministro" is one more cell of the grid, with a visible ring (E-14, G-27). */}
      <div className="samples">
        {mode === "voltage" ? <VoltageSamples network={network} /> : <LoadSamples network={network} frame={frame} />}
        {cascade && <Sample label="recién sin suministro" absent={!justDark} fault ring />}
      </div>
      {heat && <HeatKey {...heat} />}
      <p className="legend-foot">
        {mode === "voltage"
          ? `Red del modelo: ${network.lines.length} líneas entre ${network.nodes.length} subestaciones, en línea recta. El panel cuenta toda la red de IDE Energía.`
          : "% de capacidad · el grosor indica la tensión"}
      </p>
    </section>
  );
}

function VoltageSamples({ network }: { network: Network }) {
  const present = VOLTAGE_TIERS.filter((tier, i) => network.lines.some((l) => l.kv >= tier.minKv && (i === 0 || l.kv < VOLTAGE_TIERS[i - 1].minKv)));
  return <>{present.map((t) => <Sample key={t.label} label={t.label} style={{ background: t.color, height: Math.max(2, t.width + 1) }} />)}</>;
}

function LoadSamples({ network, frame }: { network: Network; frame: Frame | undefined }) {
  const edges = frame?.edges ?? {};
  const dark = new Set(frame?.dark ?? []);
  const states = network.lines.map((l) => {
    const e = edges[l.id];
    if (e?.status === "open") return "open";
    if (dark.has(l.a) && dark.has(l.b)) return "dead";
    return loadColor(e);
  });
  const has = (s: string) => states.includes(s);
  return (
    <>
      {LOAD_BANDS.map((b, i) => <Sample key={b.label} label={b.label} absent={!has(b.color)} fault={i === 3} style={{ background: b.color, height: i === 3 ? 4 : 3 }} />)}
      <Sample label="sin tensión" absent={!has("dead")} outlined style={{ background: DEAD_LINE, height: 4 }} />
      <Sample label="fuera" absent={!has("open")} dashed />
    </>
  );
}

function Sample({ label, style, absent = false, fault = false, dashed = false, ring = false, outlined = false }: { label: string; style?: React.CSSProperties; absent?: boolean; fault?: boolean; dashed?: boolean; ring?: boolean; outlined?: boolean }) {
  return (
    <div className={absent ? "sample absent" : fault ? "sample fault" : "sample"}>
      {/* A fixed-height slot centers swatches of every thickness, so all labels sit on one line. */}
      <span className="swatch-slot">
        {ring
          ? <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden><circle cx="5" cy="5" r="4" fill="none" stroke={FAULT} strokeWidth="1.5" /></svg>
          : dashed
          ? <svg width="28" height="4" viewBox="0 0 28 4" aria-hidden><path d="M0 2H28" fill="none" stroke={OPEN_LINE} strokeWidth="2" strokeDasharray="3 2.5" /></svg>
          : <span className={outlined ? "swatch outlined" : "swatch"} style={style} />}
      </span>
      <span>{label}</span>
    </div>
  );
}

/** Key of the active heat map: its name and its ramp from low to high, or the server's progress while it computes. */
function HeatKey({ kind, pending, error }: { kind: Exclude<HeatKind, "none">; pending: boolean; error: string | null }) {
  const name = HEAT_OPTIONS.find((o) => o.kind === kind)?.label ?? "";
  const [low, high] = HEAT_ENDS[kind];
  return (
    <div className="heat-key">
      <span className="heat-name">Mapa de calor: {name.toLowerCase()}</span>
      {error ? <span className="heat-status" role="alert">{error}</span> : pending ? <span className="heat-status" role="status">Calculando en el servidor…</span> : <>
        <span className="heat-ramp" style={{ background: heatGradient(kind) }} />
        <span className="heat-ends"><span>{low}</span><span>{high}</span></span>
      </>}
    </div>
  );
}

/**
 * Compact legend of a view-only network (E-28, G-06): its voltage tiers and the plant technologies it draws, always in
 * Tensión. It names no source: the panel and Ayuda do.
 */
export function RegionalMapLegend({ grid }: { grid: RegionalGrid }) {
  const tiers = VOLTAGE_TIERS.filter((tier, i) => grid.lines.some((l) => l.kv >= tier.minKv && (i === 0 || l.kv < VOLTAGE_TIERS[i - 1].minKv)));
  const techs = Object.keys(TECH_COLORS).filter((t) => grid.plants.some((p) => p.tech === t));
  const rgb = (c: number[]) => `rgb(${c[0]}, ${c[1]}, ${c[2]})`;
  return (
    <section className="legend-card compact" aria-label="Leyenda">
      <div className="legend-head"><h3>Tensión</h3><span className="unit">red solo para ver</span></div>
      <div className="samples">{tiers.map((t) => <Sample key={t.label} label={t.label} style={{ background: t.color, height: Math.max(2, t.width + 1) }} />)}</div>
      {techs.length > 0 && <>
        <h4 className="subhead">Generación por tecnología</h4>
        <div className="samples techs">{techs.map((t) => (
          <div className="sample tech" key={t}><span className="tech-dot" style={{ background: rgb(TECH_COLORS[t]) }} /><span>{TECH_NAMES[t] ?? t}</span></div>
        ))}</div>
      </>}
    </section>
  );
}
