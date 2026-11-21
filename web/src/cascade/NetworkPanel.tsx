import { useEffect, useState } from "react";
import { loadNetworkSummary, VOLTAGE_BANDS, type NetworkSummary } from "./networkSummary";
import { int } from "./text";
import { Info } from "./ui";

/** Tab "Red" (Design v5, V1): size of the whole grid by voltage. The selected element's card sits above it (SelectionCard). */
export function NetworkPanel(p: { source: string }) {
  const [summary, setSummary] = useState<NetworkSummary | null>(null);
  useEffect(() => { loadNetworkSummary().then(setSummary).catch(() => setSummary(null)); }, []);
  return (
    <>
      {summary && <Overview s={summary} />}
      <p className="source">Fuente: IDE Energía. {p.source}</p>
    </>
  );
}

function Overview({ s }: { s: NetworkSummary }) {
  const max = Math.max(...s.kmByBand, 1);
  return (
    <>
      <div className="card figures">
        <Figure value={int(s.km)} label="km de líneas" tip="Suma del largo de todas las líneas de transmisión de IDE Energía (data/processed/geo/lines.geojson)." />
        <Figure value={int(s.substations)} label="subestaciones" tip="Subestaciones registradas en IDE Energía (data/processed/geo/substations.geojson)." />
        <Figure value={int(s.mw)} label="MW instalados" tip="Potencia instalada de todas las centrales de IDE Energía (data/processed/geo/plants.geojson)." />
      </div>
      <div className="card bands">
        <div className="card-head">
          <div className="title"><h3>Líneas por tensión</h3><Info tip="Largo de las líneas de IDE Energía por nivel de tensión. Media tensión: bajo 44 kV. Las líneas sin tensión registrada no se cuentan aquí." /></div>
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
