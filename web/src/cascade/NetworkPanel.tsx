import { useEffect, useState } from "react";
import { cachedNetworkSummary, loadNetworkSummary, VOLTAGE_BANDS, type NetworkSummary } from "./networkSummary";
import { int } from "./text";
import { Info } from "./ui";

const CHILE: Origin = {
  source: "IDE Energía",
  km: "Suma del largo de todas las líneas de transmisión de la capa de líneas de IDE Energía (Ministerio de Energía).",
  substations: "Subestaciones registradas en IDE Energía (Ministerio de Energía).",
  mw: "Potencia instalada de todas las centrales de IDE Energía (Ministerio de Energía).",
  bands: "Largo de las líneas de IDE Energía por nivel de tensión. Media tensión: bajo 44 kV. Las líneas sin tensión registrada no se cuentan aquí.",
};

/** What the figures count and where they come from, for the tips and the source line. */
export interface Origin { source: string; km: string; substations: string; mw: string; bands: string }

/**
 * Tab "Red" (Design v5, V1): size of the whole grid by voltage. The selected element's card sits above it (SelectionCard).
 * Without `summary` it counts Chile's IDE Energía data; another network passes its own figures and origin.
 */
export function NetworkPanel(p: { source: string; summary?: NetworkSummary | null; origin?: Origin; viewOnly?: string; backToChile?(): void }) {
  // Seeded from the module cache, so switching back to Red never renders an empty tab (G-04, E-12).
  const [chile, setChile] = useState<NetworkSummary | null>(cachedNetworkSummary);
  const [failed, setFailed] = useState(false);
  const own = p.summary !== undefined;
  const load = () => {
    setFailed(false);
    loadNetworkSummary().then(setChile).catch((e) => { console.warn("network summary failed to load", e); setFailed(true); });
  };
  useEffect(() => { if (!own && !chile) load(); }, [own]);
  const summary = own ? p.summary : chile;
  const origin = p.origin ?? CHILE;
  return (
    <>
      {p.viewOnly && <div className="notice" role="status"><span>{p.viewOnly}</span>{p.backToChile && <button className="secondary-btn" onClick={p.backToChile}>Volver a Chile</button>}</div>}
      {summary && <Overview s={summary} o={origin} />}
      {!summary && !own && (failed
        ? <p className="note" role="alert">No se pudieron leer las cifras de la red. <button className="text-btn" onClick={load}>Reintentar</button></p>
        : <div className="card loading" role="status" aria-live="polite"><span className="loading-bar" /><p>Cargando las cifras de la red</p></div>)}
      <p className="source">Fuente: {origin.source}. {p.source}</p>
    </>
  );
}

function Overview({ s, o }: { s: NetworkSummary; o: Origin }) {
  const max = Math.max(...s.kmByBand, 1);
  return (
    <>
      <div className="card figures">
        <Figure value={int(s.km)} label="km de líneas" tip={o.km} />
        <Figure value={int(s.substations)} label="subestaciones" tip={o.substations} />
        <Figure value={int(s.mw)} label="MW instalados" tip={o.mw} />
      </div>
      <div className="card bands">
        <div className="card-head">
          <div className="title"><h3>Líneas por tensión</h3><Info tip={o.bands} /></div>
          <span className="unit">km</span>
        </div>
        {VOLTAGE_BANDS.map((b, i) => (
          <div className="band" key={b.label}>
            <span className="sample" style={{ background: b.color, height: b.stroke }} />
            <span className="band-label">{b.label}</span>
            <span className="track"><span style={{ width: `${(s.kmByBand[i] / max) * 100}%`, background: b.color }} /></span>
            <span className="band-value">{int(s.kmByBand[i])}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function Figure({ value, label, tip }: { value: string; label: string; tip: string }) {
  return <div className="figure"><div className="value-row"><b>{value}</b><Info tip={tip} /></div><span>{label}</span></div>;
}
