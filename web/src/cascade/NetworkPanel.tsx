import { useEffect, useState } from "react";
import { loadNetworkSummary, VOLTAGE_BANDS, type NetworkSummary } from "./networkSummary";
import { fmt, formatPeople } from "../lib/format";
import { lineName, ZONES } from "./text";
import type { BusState, Frame, Network } from "./types";


/** Tab "Red": size of the grid by voltage, and the detail of the selected substation or cut line. */
export function NetworkPanel(p: { network: Network; buses: Record<string, BusState>; frame: Frame | undefined; node: string | null; line: string | null; clearNode(): void; cutLine(id: string): void }) {
  const [summary, setSummary] = useState<NetworkSummary | null>(null);
  useEffect(() => { loadNetworkSummary().then(setSummary).catch(() => setSummary(null)); }, []);
  return (
    <section className="network">
      {p.node && <NodeCard {...p} node={p.node} />}
      {p.line && !p.node && <LineCard network={p.network} frame={p.frame} line={p.line} />}
      {summary && <Overview s={summary} />}
    </section>
  );
}

function Overview({ s }: { s: NetworkSummary }) {
  const max = Math.max(...s.kmByBand, 1);
  return (
    <>
      <div className="stats"><div><b>{fmt(s.km)}</b><span>km de líneas</span></div><div><b>{fmt(s.substations)}</b><span>subestaciones</span></div><div><b>{fmt(s.mw)}</b><span>MW instalados</span></div></div>
      <div className="card">
        <div className="card-head"><h3>Líneas por tensión</h3><span>km</span></div>
        {VOLTAGE_BANDS.map((b, i) => (
          <div className="bar-row" key={b.label}>
            <span className="swatch" style={{ background: b.color }} /><span className="bar-label">{b.label}</span>
            <span className="track"><span style={{ width: `${(s.kmByBand[i] / max) * 100}%`, background: b.color }} /></span><span className="bar-value">{fmt(s.kmByBand[i])}</span>
          </div>
        ))}
      </div>
      <p className="muted">Fuente: IDE Energía. Mapa base: Mapbox.</p>
    </>
  );
}

function NodeCard(p: { network: Network; buses: Record<string, BusState>; frame: Frame | undefined; node: string; clearNode(): void; cutLine(id: string): void }) {
  const n = p.network.nodes.find((x) => x.id === p.node);
  if (!n) return null;
  const b = p.buses[n.id];
  const dark = p.frame?.dark.includes(n.id);
  const lines = p.network.lines.filter((l) => l.a === n.id || l.b === n.id);
  return (
    <div className="card">
      <div className="card-head"><h3>{n.name}</h3><button className="link" onClick={p.clearNode}>Cerrar</button></div>
      <p className="muted">{Math.round(n.kv)} kV · {ZONES[n.zone] ?? ZONES.centro_sur}{dark ? " · sin energía" : ""}</p>
      <div className="stats"><div><b>{fmt(b?.gen_mw ?? 0)} MW</b><span>generación</span></div><div><b>{fmt(b?.load_mw ?? 0)} MW</b><span>demanda</span></div><div><b>{formatPeople(b?.people ?? 0)}</b><span>personas</span></div></div>
      <h4>Líneas conectadas · {lines.length}</h4>
      {lines.map((l) => {
        const e = p.frame?.edges[l.id];
        return <button className="row-btn" key={l.id} onClick={() => p.cutLine(l.id)} title="Cortar esta línea"><span>{lineName(p.network, l.id)}</span><span>{e ? `${Math.round(e.loading * 100)}%` : "s/d"}</span></button>;
      })}
      <p className="muted">Clic en una línea de la lista la corta.</p>
    </div>
  );
}

function LineCard({ network, frame, line }: { network: Network; frame: Frame | undefined; line: string }) {
  const l = network.lines.find((x) => x.id === line);
  if (!l) return null;
  const e = frame?.edges[line];
  return (
    <div className="card">
      <div className="card-head"><h3>{lineName(network, line)}</h3></div>
      <div className="stats"><div><b>{fmt(l.capacity_mw)} MW</b><span>capacidad</span></div><div><b>{e ? fmt(Math.abs(e.flow_mw)) : "s/d"} MW</b><span>flujo</span></div><div><b>{e ? `${Math.round(e.loading * 100)}%` : "s/d"}</b><span>de su capacidad</span></div></div>
      <p className="muted">{e?.status === "open" ? "Abierta en esta etapa." : e?.status === "overload" ? "Sobre su capacidad." : "En servicio."} Agrupa {l.branches.length} elemento(s) del modelo (circuitos y transformadores).</p>
    </div>
  );
}
