import { useEffect, useState } from "react";
import { loadNetworkSummary, VOLTAGE_BANDS, type NetworkSummary } from "./networkSummary";
import { formatPeople, int, lineName, pct, placeName, zoneName } from "./text";
import type { BusState, Frame, Network } from "./types";
import { Info } from "./ui";

/** Tab "Red" (Design v5, V1): size of the whole grid by voltage, and the detail of the selected substation. */
export function NetworkPanel(p: { network: Network; buses: Record<string, BusState>; frame: Frame | undefined; node: string | null; clearNode(): void; cutLine(id: string): void; source: string }) {
  const [summary, setSummary] = useState<NetworkSummary | null>(null);
  useEffect(() => { loadNetworkSummary().then(setSummary).catch(() => setSummary(null)); }, []);
  return (
    <>
      {p.node && <NodeCard {...p} node={p.node} />}
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

function NodeCard(p: { network: Network; buses: Record<string, BusState>; frame: Frame | undefined; node: string; clearNode(): void; cutLine(id: string): void }) {
  const n = p.network.nodes.find((x) => x.id === p.node);
  if (!n) return null;
  const b = p.buses[n.id];
  const dark = p.frame?.dark.includes(n.id);
  const lines = p.network.lines.filter((l) => l.a === n.id || l.b === n.id);
  return (
    <div className="card node">
      <div className="card-head">
        <div className="title"><h3>{placeName(n.name)}</h3></div>
        <button className="text-btn" onClick={p.clearNode}>Cerrar</button>
      </div>
      <p className="meta">{Math.round(n.kv)} kV · {zoneName(n.zone)}{dark ? " · sin suministro" : ""}</p>
      <div className="mini-figures">
        <div><b>{int(b?.gen_mw ?? 0)} <small>MW</small></b><span>generación</span></div>
        <div><b>{int(b?.load_mw ?? 0)} <small>MW</small></b><span>demanda</span></div>
        <div><b>{formatPeople(b?.people ?? 0)}</b><span>personas</span></div>
      </div>
      <div className="list-head"><span>Líneas conectadas · {lines.length}</span><span>carga</span></div>
      {lines.map((l) => {
        const e = p.frame?.edges[l.id];
        return (
          <button className="row-btn" key={l.id} onClick={() => p.cutLine(l.id)} title="Sacar de servicio esta línea">
            <span>{lineName(p.network, l.id)}</span><span className="num">{e?.status === "open" ? "fuera" : e ? pct(e.loading) : "s/d"}</span>
          </button>
        );
      })}
      <p className="meta">Clic en una línea de la lista la saca de servicio. Generación, demanda y personas: punto de operación del motor Sub50.</p>
    </div>
  );
}
