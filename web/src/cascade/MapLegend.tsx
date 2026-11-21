import { DEAD_LINE, LOAD_BANDS, OPEN_LINE, VOLTAGE_TIERS, loadColor, type ColorMode } from "./layers";
import type { Frame, Network } from "./types";
import { Chevron } from "./ui";

/**
 * Legend card at the bottom right (Design v5). It lists line samples, never a segmented bar. The load legend always
 * shows the same six items; items absent from the current frame keep a 40 % swatch.
 */
export function MapLegend({ mode, setMode, network, frame }: { mode: ColorMode; setMode(m: ColorMode): void; network: Network; frame: Frame | undefined }) {
  return (
    <section className="legend-card" aria-label="Leyenda">
      <div className="legend-head">
        <h3>Color de líneas</h3>
        <label className="legend-mode">
          <span>{mode === "voltage" ? "Tensión" : "Carga"}</span><Chevron />
          <select aria-label="Qué indica el color de las líneas" value={mode} onChange={(e) => setMode(e.target.value as ColorMode)}>
            <option value="voltage">Tensión</option>
            <option value="load">Carga</option>
          </select>
        </label>
      </div>
      {mode === "voltage" ? <VoltageSamples network={network} /> : <LoadSamples network={network} frame={frame} />}
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
  return <div className="samples">{present.map((t) => <Sample key={t.label} label={t.label} style={{ background: t.color, height: Math.max(2, t.width + 1) }} />)}</div>;
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
    <div className="samples">
      {LOAD_BANDS.map((b, i) => <Sample key={b.label} label={b.label} absent={!has(b.color)} fault={i === 3} style={{ background: b.color, height: i === 3 ? 4 : 3 }} />)}
      <Sample label="sin tensión" absent={!has("dead")} style={{ background: DEAD_LINE, height: 4, outline: "1px solid #FFFFFF40" }} />
      <Sample label="fuera" absent={!has("open")} dashed />
    </div>
  );
}

function Sample({ label, style, absent = false, fault = false, dashed = false }: { label: string; style?: React.CSSProperties; absent?: boolean; fault?: boolean; dashed?: boolean }) {
  return (
    <div className={absent ? "sample absent" : fault ? "sample fault" : "sample"}>
      {/* A fixed-height slot centers swatches of every thickness, so all labels sit on one line. */}
      <span className="swatch-slot">
        {dashed
          ? <svg width="28" height="4" viewBox="0 0 28 4" aria-hidden><path d="M0 2H28" fill="none" stroke={OPEN_LINE} strokeWidth="2" strokeDasharray="3 2.5" /></svg>
          : <span className="swatch" style={style} />}
      </span>
      <span>{label}</span>
    </div>
  );
}
