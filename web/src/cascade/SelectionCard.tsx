import type { Pick } from "./clicks";
import { loadColor } from "./layers";
import { lineStateAt } from "./simulation";
import { formatPeople, int, lineName, pct, placeName, zoneName } from "./text";
import type { BusState, Frame, NetLine, Network } from "./types";
import { Info } from "./ui";

interface Props {
  network: Network; buses: Record<string, BusState>; frame: Frame | undefined; selection: Pick; cut: string | null; year: number | undefined;
  select(pick: Pick): void; clear(): void; cutLine(id: string): void; restore(): void;
}

const TOPOLOGY_TIP = (year: number | undefined) =>
  `Red reducida del modelo Sub50 (web/public/cache/network-${year ?? "<año>"}.json): las ramas de PyPSA-CL entre las mismas dos subestaciones se fusionan en un corredor y su capacidad es la suma de sus MVA nominales.`;
const FLOW_TIP = "Flujo DC calculado por el motor Sub50 en el segundo actual de la simulación (sin tensión ni potencia reactiva).";
const STATUS_TIP = "Estado en el segundo actual según el motor Sub50: una línea sobre el 120 % de su capacidad se abre; sin tensión significa que sus dos extremos quedaron sin suministro.";

/** Detail of the selected line or substation, at the top of the panel in both tabs. */
export function SelectionCard(p: Props) {
  if (p.selection.kind === "line") {
    const line = p.network.lines.find((l) => l.id === p.selection.id);
    return line ? <LineCard {...p} line={line} /> : null;
  }
  return <NodeCard {...p} node={p.selection.id} />;
}

function LineCard(p: Props & { line: NetLine }) {
  const { line } = p;
  const s = lineStateAt(line, p.frame);
  const edge = p.frame?.edges[line.id];
  const name = (id: string) => placeName(p.network.nodes.find((n) => n.id === id)?.name ?? id);
  const isCut = p.cut === line.id;
  const branches = line.branches.length; // model branches, not physical circuits: one branch can stand for several circuits
  return (
    <div className="card selection">
      <div className="card-head">
        <div className="title"><h3>{lineName(p.network, line.id)}</h3></div>
        <button className="text-btn" onClick={p.clear}>Cerrar</button>
      </div>
      <div className="value-row meta">
        <span>Línea de {Math.round(line.kv)} kV · {branches === 1 ? "1 rama del modelo" : `${branches} ramas del modelo fusionadas`}</span>
        <Info tip={TOPOLOGY_TIP(p.year)} />
      </div>
      <div className="mini-figures ruled">
        <div><div className="value-row"><b>{int(line.capacity_mw)} <small>MW</small></b><Info tip={TOPOLOGY_TIP(p.year)} /></div><span>capacidad</span></div>
        <div>
          <div className="value-row"><b>{int(s.flowMw)} <small>MW</small></b><Info tip={FLOW_TIP} /></div>
          <span>flujo</span>
        </div>
        <div>
          <div className="value-row"><b className={s.loading > 1 ? "fault" : ""}>{pct(s.loading)}</b><Info tip={`Flujo sobre capacidad. ${FLOW_TIP}`} /></div>
          <span className="load-bar"><span style={{ width: `${Math.min(1, s.loading) * 100}%`, background: loadColor(edge) }} /></span>
        </div>
      </div>
      {s.flowMw > 0 && <p className="meta">Flujo de {name(s.from)} a {name(s.to)}.</p>}
      <div className="value-row status-row">
        <span>Estado: <b className={s.status === "sobrecargada" ? "fault" : ""}>{s.status}</b>{s.atLimit ? ", al límite de su capacidad" : ""}{isCut ? " (corte de este escenario)" : ""}</span>
        <Info tip={STATUS_TIP} />
      </div>
      <div className="list-head"><span>Extremos</span><span>tensión</span></div>
      {[line.a, line.b].map((id) => {
        const n = p.network.nodes.find((x) => x.id === id);
        return (
          <button className="row-btn" key={id} onClick={() => p.select({ kind: "node", id })}>
            <span>{name(id)}{p.frame?.dark.includes(id) ? " · sin suministro" : ""}</span><span className="num">{n ? `${Math.round(n.kv)} kV` : ""}</span>
          </button>
        );
      })}
      <div className="actions">
        {isCut
          ? <button className="primary-btn" onClick={p.restore}>Reponer línea</button>
          : <button className="primary-btn" onClick={() => p.cutLine(line.id)}>Sacar de servicio</button>}
        <span className="meta">{isCut ? "Vuelve al caso base en este punto de operación." : "O doble clic en la línea del mapa."}</span>
      </div>
    </div>
  );
}

function NodeCard(p: Props & { node: string }) {
  const n = p.network.nodes.find((x) => x.id === p.node);
  if (!n) return null;
  const b = p.buses[n.id];
  const dark = p.frame?.dark.includes(n.id);
  const lines = p.network.lines.filter((l) => l.a === n.id || l.b === n.id);
  const opTip = (what: string) => `${what} de la subestación en el punto de operación del motor Sub50 (web/public/cache/<punto>/buses.json).`;
  return (
    <div className="card selection">
      <div className="card-head">
        <div className="title"><h3>{placeName(n.name)}</h3></div>
        <button className="text-btn" onClick={p.clear}>Cerrar</button>
      </div>
      <p className="meta">{Math.round(n.kv)} kV · {zoneName(n.zone)}{dark ? " · sin suministro" : ""}</p>
      <div className="mini-figures">
        <div><div className="value-row"><b>{int(b?.gen_mw ?? 0)} <small>MW</small></b><Info tip={opTip("Generación")} /></div><span>generación</span></div>
        <div><div className="value-row"><b>{int(b?.load_mw ?? 0)} <small>MW</small></b><Info tip={opTip("Demanda")} /></div><span>demanda</span></div>
        <div><div className="value-row"><b>{formatPeople(b?.people ?? 0)}</b><Info tip={opTip("Personas asignadas")} /></div><span>personas</span></div>
      </div>
      <div className="list-head"><span>Líneas conectadas · {lines.length}</span><span>carga</span></div>
      {lines.map((l) => {
        const e = p.frame?.edges[l.id];
        return (
          <button className="row-btn" key={l.id} onClick={() => p.select({ kind: "line", id: l.id })}>
            <span>{lineName(p.network, l.id)}</span><span className="num">{e?.status === "open" ? "fuera" : e ? pct(e.loading) : "s/d"}</span>
          </button>
        );
      })}
      <p className="meta">Clic en una línea de la lista para ver su detalle. Carga: flujo DC del motor Sub50 en el segundo actual.</p>
    </div>
  );
}
