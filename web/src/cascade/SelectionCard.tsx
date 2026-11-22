import { useEffect, useState } from "react";
import type { Pick } from "./clicks";
import { factorOf, MAX_FACTOR, parseFactor, type Edits, type Target } from "./edits";
import type { Prepared, Supply } from "./gridsApi";
import { loadColor } from "./layers";
import { lineStateAt } from "./simulation";
import { formatPeople, int, lineName, pct, pct2, placeName, zoneName } from "./text";
import type { BusState, Frame, NetLine, Network } from "./types";
import { Chevron, Info } from "./ui";

interface Props {
  /** network: the reduced network on the map. buses: gen, load and people per bus at the point. frame: the cascade frame at the
   *  playhead (undefined before a timeline). selection: the clicked line or substation. cut: id of the line cut now, or null.
   *  year: network year, for the topology tip. Callbacks: select a row of a list, clear the selection, cut the line, restore
   *  the cut, shut down or power on a substation. */
  network: Network; buses: Record<string, BusState>; frame: Frame | undefined; selection: Pick; cut: string | null; year: number | undefined;
  /** True when the selected substation is shut down (every one of its lines open). */
  shutDown: boolean;
  select(pick: Pick): void; clear(): void; cutLine(id: string): void; restore(): void; shutdown(nodeId: string): void; powerOn(nodeId: string): void;
  /** The user's changes, to edit this component in place; null where components cannot be edited. */
  edits: Edits | null;
  /** The prepared grid of the changes (POST /grids/prepare) and the supply after the last simulation, if any. */
  prepared: Prepared | null; supply: Supply | null;
  setFactor(target: Target, id: string, factor: number): void;
}

const PREPARED_TIP = "Valor de la red con tus cambios, antes de cualquier falla. Cada persona agregada suma 0,389 veces la demanda por persona del punto de operación: la parte de hogares y comercio (supuesto del modelo).";
const SUPPLY_TIP = "Personas que esta subestación debería alimentar antes de la falla y las que sigue alimentando cuando la cascada se asienta, repartidas según el flujo de potencia del modelo (supuesto del modelo).";

/** The value of `key` of a bus after every change of the prepared scenario, or null when no change touched it. */
function preparedValue(prepared: Prepared | null, id: string, key: "load_mw" | "gen_mw" | "people"): number | null {
  let out: number | null = null;
  for (const c of prepared?.changes ?? []) {
    for (const e of c.elements ?? []) {
      if (e.id !== id) continue;
      const v = e[key];
      if (typeof v === "number") out = v;
      else if (Array.isArray(v)) out = v[1];
    }
  }
  return out;
}

/**
 * A factor typed in place; it applies on Enter or when the field loses focus, so each keystroke does not simulate. A blank
 * or out-of-range value keeps the previous factor and says why next to the field (A2-02).
 */
function FactorInput({ label, value, target, set }: { label: string; value: number; target: Target; set(f: number): void }) {
  const [text, setText] = useState(String(value));
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setText(String(value)), [value]);
  const commit = () => {
    const r = parseFactor(text, target);
    if ("factor" in r) { setError(null); if (r.factor !== value) set(r.factor); }
    else { setError(r.error); setText(String(value)); }
  };
  const id = `factor-${target}`;
  return (
    <>
      <label className="factor-input">
        <span>{label}</span>
        <span className="value-row">×<input type="number" min={target === "lines" ? 0.01 : 0} max={MAX_FACTOR} step={0.1} value={text} aria-label={`Factor de ${label.toLowerCase()}`}
          aria-invalid={error ? true : undefined} aria-describedby={error ? id : undefined}
          onChange={(e) => { setText(e.target.value); setError(null); }} onBlur={commit} onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()} /></span>
      </label>
      {error && <p className="field-error" id={id} role="alert">{error} Se mantiene × {String(value).replace(".", ",")}.</p>}
    </>
  );
}

const TOPOLOGY_TIP = (year: number | undefined) =>
  `Red resumida del modelo Sub50${year ? ` (red de ${year})` : ""}: los circuitos del modelo PyPSA-CL entre las mismas dos subestaciones se funden en un corredor, y su capacidad es la suma de sus capacidades nominales.`;
const FLOW_TIP = "Flujo de potencia calculado por el motor Sub50 en el segundo actual de la simulación (modelo de corriente continua: sin tensión ni potencia reactiva).";
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
  const capacity = factorOf(p.edits ?? { lines: [], buses: [] }, "lines", line.id);
  return (
    <div className="card selection">
      <div className="card-head">
        <div className="title"><h3>{lineName(p.network, line.id)}</h3></div>
        <button className="text-btn" onClick={p.clear}>Cerrar</button>
      </div>
      <div className="value-row meta">
        <span>Línea de {Math.round(line.kv)} kV · {branches === 1 ? "1 circuito del modelo" : `${branches} circuitos del modelo fundidos en uno`}</span>
        <Info tip={TOPOLOGY_TIP(p.year)} />
      </div>
      <div className="mini-figures ruled">
        <div><div className="value-row"><b>{int(line.capacity_mw)} <small>MW</small></b><Info tip={TOPOLOGY_TIP(p.year)} /></div><span>capacidad</span></div>
        <div><div className="value-row"><b>{int(s.flowMw)} <small>MW</small></b><Info tip={FLOW_TIP} /></div><span>flujo</span></div>
        <div><div className="value-row"><b className={s.loading > 1 ? "fault" : ""}>{pct(s.loading)}</b><Info tip={`Flujo sobre capacidad. ${FLOW_TIP}`} /></div><span>de su capacidad</span></div>
      </div>
      {/* The load bar spans the card in its load band colour (E-22). */}
      <span className="load-bar" role="img" aria-label={`Carga ${pct(s.loading)}`}><span style={{ width: `${Math.min(1, s.loading) * 100}%`, background: loadColor(edge) }} /></span>
      {s.flowMw > 0 && <p className="meta">Flujo de {name(s.from)} a {name(s.to)}.</p>}
      <div className="value-row status-row">
        <span>Estado: <b className={s.status === "sobrecargada" ? "fault" : ""}>{s.status}</b>{s.atLimit ? ", al límite de su capacidad" : ""}{isCut ? " (corte de este escenario)" : ""}</span>
        <Info tip={STATUS_TIP} />
      </div>
      <div className="actions">
        {isCut
          ? <button className="primary-btn" onClick={p.restore}>Volver a conectar</button>
          : <button className="primary-btn" onClick={() => p.cutLine(line.id)}>Sacar de servicio</button>}
        <span className="meta">{isCut ? "Vuelve al caso base en este punto de operación." : "O clic otra vez en la línea del mapa."}</span>
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
      {p.edits && (
        <EditBlock changed={capacity !== 1}>
          <FactorInput label="Capacidad" target="lines" value={capacity} set={(f) => p.setFactor("lines", line.id, f)} />
          <p className="meta">Multiplica la capacidad de la línea antes de cualquier falla. 1 la deja como está.</p>
        </EditBlock>
      )}
    </div>
  );
}

/** "Modificar valores": the factor fields behind a closed disclosure, after the action (E-22, F-21); open while a factor is set. */
function EditBlock({ changed, children }: { changed: boolean; children: React.ReactNode }) {
  return (
    <details className="disclosure-block edit-block" open={changed || undefined}>
      <summary><Chevron dir="right" color="currentColor" /><span>Modificar valores</span>{changed && <span className="unit">con cambios</span>}</summary>
      <div className="edit-fields">
        <div className="list-head"><span>Valor</span><span>factor</span></div>
        {children}
      </div>
    </details>
  );
}

function NodeCard(p: Props & { node: string }) {
  const n = p.network.nodes.find((x) => x.id === p.node);
  if (!n) return null;
  const b = p.buses[n.id];
  const dark = p.frame?.dark.includes(n.id);
  const lines = p.network.lines.filter((l) => l.a === n.id || l.b === n.id);
  const opTip = (what: string) => `${what} de la subestación en el punto de operación elegido, según el modelo Sub50 (despacho simulado con PyPSA-CL, no medido).`;
  return (
    <div className="card selection">
      <div className="card-head">
        <div className="title"><h3>{placeName(n.name)}</h3></div>
        <button className="text-btn" onClick={p.clear}>Cerrar</button>
      </div>
      <p className="meta">{Math.round(n.kv)} kV · {zoneName(n.zone)}{p.shutDown ? " · apagada" : dark ? " · sin suministro" : ""}</p>
      <div className="mini-figures">
        <div><div className="value-row"><b>{int(b?.gen_mw ?? 0)} <small>MW</small></b><Info tip={opTip("Generación")} /></div><span>generación</span></div>
        <div><div className="value-row"><b>{int(b?.load_mw ?? 0)} <small>MW</small></b><Info tip={opTip("Demanda")} /></div><span>demanda</span></div>
        <div><div className="value-row"><b>{formatPeople(b?.people ?? 0)}</b><Info tip={opTip("Personas asignadas")} /></div><span>personas</span></div>
      </div>
      <PreparedFigures p={p} id={n.id} />
      <SupplyRow p={p} id={n.id} />
      {lines.length > 0 && (
        <div className="actions">
          {p.shutDown
            ? <button className="primary-btn" onClick={() => p.powerOn(n.id)}>Volver a encender</button>
            : <button className="primary-btn" onClick={() => p.shutdown(n.id)}>Apagar subestación</button>}
          <span className="meta">{p.shutDown ? "Vuelve a operar con sus líneas." : "Sale de servicio con su demanda y su generación. O clic otra vez en la subestación del mapa."}</span>
        </div>
      )}
      <div className="list-head"><span>Líneas conectadas · {lines.length}</span><span>carga</span></div>
      {lines.map((l) => {
        const e = p.frame?.edges[l.id];
        return (
          <button className="row-btn" key={l.id} onClick={() => p.select({ kind: "line", id: l.id })}>
            <span>{lineName(p.network, l.id)}</span><span className="num">{e?.status === "open" ? "fuera" : e ? pct(e.loading) : "s/d"}</span>
          </button>
        );
      })}
      <p className="meta">Clic en una línea de la lista para ver su detalle. Carga: flujo del motor Sub50 en el segundo actual.</p>
      {p.edits && (() => {
        const f = { population: factorOf(p.edits, "population", n.id), demand: factorOf(p.edits, "demand", n.id), generation: factorOf(p.edits, "generation", n.id) };
        return (
          <EditBlock changed={f.population !== 1 || f.demand !== 1 || f.generation !== 1}>
            <FactorInput label="Personas" target="population" value={f.population} set={(x) => p.setFactor("population", n.id, x)} />
            <FactorInput label="Demanda" target="demand" value={f.demand} set={(x) => p.setFactor("demand", n.id, x)} />
            <FactorInput label="Generación" target="generation" value={f.generation} set={(x) => p.setFactor("generation", n.id, x)} />
            <p className="meta">Más personas suben la demanda de hogares y comercio; la de minería e industria no cambia. La demanda también puede cambiar sola. La isla redespacha lo que falte. 1 deja el valor como está.</p>
          </EditBlock>
        );
      })()}
    </div>
  );
}

/** The prepared values of the bus when a change touched it, next to the base ones above. */
function PreparedFigures({ p, id }: { p: Props; id: string }) {
  const gen = preparedValue(p.prepared, id, "gen_mw");
  const load = preparedValue(p.prepared, id, "load_mw");
  const people = preparedValue(p.prepared, id, "people");
  if (gen === null && load === null && people === null) return null;
  return (
    <div className="mini-figures prepared">
      <div><div className="value-row"><b>{gen === null ? "=" : <>{int(gen)} <small>MW</small></>}</b><Info tip={PREPARED_TIP} /></div><span>generación preparada</span></div>
      <div><div className="value-row"><b>{load === null ? "=" : <>{int(load)} <small>MW</small></>}</b><Info tip={PREPARED_TIP} /></div><span>demanda preparada</span></div>
      <div><div className="value-row"><b>{people === null ? "=" : formatPeople(people)}</b><Info tip={PREPARED_TIP} /></div><span>personas preparadas</span></div>
    </div>
  );
}

/** People this generating substation should feed against the people it still feeds after the last simulation. */
function SupplyRow({ p, id }: { p: Props; id: string }) {
  const row = p.supply?.sources.find((r) => r.id === id);
  if (!row) return null;
  return (
    <div className="value-row status-row">
      <span>Debería alimentar a <b>{formatPeople(row.should_feed)}</b> personas y alimenta a <b className={row.pct_fed < 100 ? "fault" : ""}>{formatPeople(row.feeds)}</b> ({pct2(row.pct_fed)}).</span>
      <Info tip={SUPPLY_TIP} />
    </div>
  );
}

