import { useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { lineName } from "../cascade/text";
import type { SessionNetwork } from "../cascade/types";
import { nearestBus } from "./geo";
import { addElement, deleteElement, resetSession, updateElement, type Kind } from "./sessionApi";
import type { Edit } from "./useSession";

type Sub = "buses" | "lines" | "generators" | "loads";
const SUBS: [Sub, string][] = [["buses", "Barras"], ["lines", "Líneas"], ["generators", "Generadores"], ["loads", "Cargas y datacenters"]];
const TECHS = ["solar", "eolica", "hidro", "termica", "bioenergia", "geotermica"];
const LIMIT = 60;
type Values = Record<string, string>;
type FieldType = "text" | "number" | "kv" | "tech" | "kind";
interface Spec { key: string; label: string; type?: FieldType }
export type Pick = (onPoint: (lon: number, lat: number) => void) => void;
const fmt = (n: number) => Math.round(n).toLocaleString("es-CL");

/** Tab "Datos": the session's editable copy of the 188-bus network. Every value it adds is an assumption. */
export function DataPanel(p: { network: SessionNetwork; edit: Edit; pick: Pick; picking: boolean }) {
  const [sub, setSub] = useState<Sub>("loads");
  const n = p.network;
  const kvs = [...new Set(n.nodes.map((x) => x.kv))].sort((a, b) => a - b);
  const reset = () => { if (confirm("¿Borrar todos los cambios de esta sesión? Afecta a todos sus participantes.")) p.edit((sid, rev) => resetSession(sid, rev)); };
  return (
    <section className="data-panel">
      <div className="card">
        <div className="card-head"><h3>Caso base de la sesión</h3><button className="text-btn" onClick={reset}>Restablecer</button></div>
        <div className="figures">
          <div className="figure"><b>{Math.round(n.baseline.max_loading * 100)}%</b><span>carga máxima de una línea</span></div>
          <div className="figure"><b>{n.baseline.overloaded.length}</b><span>líneas sobrecargadas</span></div>
          <div className="figure"><b>{fmt(n.baseline.load_shed_mw)} MW</b><span>desconectados sin corte</span></div>
        </div>
        {n.balance.map((b, i) => <p key={i} className="meta"><span className="tag assumption">supuesto (sesión)</span> Redespacho de {fmt(b.redispatch_mw)} MW en {Object.keys(b.buses).length} barras. {b.rule}</p>)}
        {n.warnings.map((w, i) => <p key={i} className="note warn">{w.message}</p>)}
      </div>
      {p.picking && <p className="meta">Haz clic en el mapa para elegir la ubicación.</p>}
      <div className="seg" role="tablist">
        {SUBS.map(([k, label]) => <button key={k} role="tab" aria-selected={sub === k} className={sub === k ? "on" : ""} onClick={() => setSub(k)}>{label}</button>)}
      </div>
      {sub === "buses" && <Buses {...p} kvs={kvs} />}
      {sub === "lines" && <Lines {...p} kvs={kvs} />}
      {sub === "generators" && <Elements {...p} kind="generators" />}
      {sub === "loads" && <Elements {...p} kind="loads" />}
    </section>
  );
}
type Props = { network: SessionNetwork; edit: Edit; pick: Pick; kvs?: number[] };

function Buses(p: Props) {
  const [filter, setFilter] = useState("");
  const add = useForm({ name: "", kv: "220", lat: "", lon: "" });
  const rows = _filter(p.network.nodes, filter, (x) => `${x.id} ${x.name}`).sort((a, b) => Number(b.origin === "session") - Number(a.origin === "session"));
  return <>
    <h4>Agregar barra (subestación nueva)</h4>
    <Form specs={[{ key: "name", label: "Nombre" }, { key: "kv", label: "kV", type: "kv" }, { key: "lat", label: "Latitud", type: "number" }, { key: "lon", label: "Longitud", type: "number" }]} kvs={p.kvs} f={add} submit="Agregar barra"
      onSubmit={(v) => p.edit((sid, rev) => addElement(sid, "buses", v, rev))}>
      <button type="button" className="btn" onClick={() => p.pick((lon, lat) => add.merge({ lon: lon.toFixed(4), lat: lat.toFixed(4) }))}>Elegir en el mapa</button>
    </Form>
    <p className="meta">Una barra nueva queda aislada hasta que le agregues una línea (pestaña Líneas).</p>
    <Filter value={filter} set={setFilter} count={rows.length} />
    {rows.slice(0, LIMIT).map((x) => {
      const b = p.network.buses[x.id];
      return <Row key={x.id} id={x.id} kind="buses" edit={p.edit} origin={x.origin} assumption={x.is_assumption} inService={x.in_service !== false} kvs={p.kvs}
        title={`${x.name} · ${Math.round(x.kv)} kV`} detail={`${fmt(b?.load_mw ?? 0)} MW demanda · ${fmt(b?.gen_mw ?? 0)} MW generación`}
        specs={[{ key: "name", label: "Nombre" }, { key: "kv", label: "kV", type: "kv" }, { key: "load_mw", label: "Demanda MW", type: "number" }, { key: "gen_mw", label: "Generación MW", type: "number" }, { key: "sync_mw", label: "Sincrónica MW", type: "number" }, { key: "inertia_mws", label: "Inercia MWs", type: "number" }]}
        init={{ name: x.name, kv: String(x.kv), load_mw: String(b?.load_mw ?? ""), gen_mw: String(b?.gen_mw ?? ""), sync_mw: "", inertia_mws: "" }} />;
    })}
  </>;
}

function Lines(p: Props) {
  const [filter, setFilter] = useState("");
  const add = useForm({ a: "", b: "", kv: "220", capacity_mw: "", name: "" });
  const net = p.network;
  const rows = _filter(net.lines, filter, (l) => `${l.id} ${l.a} ${l.b} ${lineName(net, l.id)}`).sort((a, b) => Number(b.origin === "session") - Number(a.origin === "session"));
  return <>
    <h4>Agregar línea</h4>
    <Form specs={[{ key: "a", label: "Barra A (B###)" }, { key: "b", label: "Barra B (B###)" }, { key: "kv", label: "kV", type: "kv" }, { key: "capacity_mw", label: "Capacidad MW", type: "number" }, { key: "name", label: "Nombre (opcional)" }]}
      kvs={p.kvs} f={add} submit="Agregar línea" onSubmit={(v) => p.edit((sid, rev) => addElement(sid, "lines", v, rev))} />
    <p className="meta">La reactancia se estima con el largo y la tensión de la línea (supuesto).</p>
    {net.out_of_service.lines.length > 0 && <>
      <h4>Fuera de servicio · {net.out_of_service.lines.length}</h4>
      {net.out_of_service.lines.map((id) => <div className="data-line" key={id}><span>{id}</span><button className="text-btn" onClick={() => p.edit((sid, rev) => updateElement(sid, "lines", id, { in_service: true }, rev))}>Poner en servicio</button></div>)}
    </>}
    <Filter value={filter} set={setFilter} count={rows.length} />
    {rows.slice(0, LIMIT).map((l) => <Row key={l.id} id={l.id} kind="lines" edit={p.edit} origin={l.origin} assumption={l.is_assumption} inService
      title={`${l.id} · ${lineName(net, l.id)}`} detail={`${fmt(l.capacity_mw)} MW de capacidad`}
      specs={[{ key: "capacity_mw", label: "Capacidad MW", type: "number" }, { key: "x_pu", label: "Reactancia (pu)", type: "number" }]}
      init={{ capacity_mw: String(l.capacity_mw), x_pu: String(l.x_pu) }} />)}
  </>;
}

function Elements(p: Props & { kind: "loads" | "generators" }) {
  const loads = p.kind === "loads";
  const add = useForm(loads ? { kind: "datacenter", name: "", mw: "", bus: "", lat: "", lon: "" } : { tech: "solar", name: "", mw: "", bus: "" });
  const [near, setNear] = useState<string | null>(null);
  const connect = () => {
    const best = nearestBus(p.network.nodes, Number(add.values.lon), Number(add.values.lat), 220);
    if (best) { add.merge({ bus: best.node.id }); setNear(`${best.node.id} · ${best.node.name} (${Math.round(best.node.kv)} kV) a ${best.km.toFixed(1).replace(".", ",")} km`); }
    else setNear("No hay subestaciones de 220 kV o más en servicio.");
  };
  const rows = loads ? p.network.loads : p.network.generators;
  const specs: Spec[] = loads
    ? [{ key: "kind", label: "Tipo", type: "kind" }, { key: "name", label: "Nombre" }, { key: "mw", label: "MW", type: "number" }, { key: "bus", label: "Barra (B###)" }, { key: "lat", label: "Latitud", type: "number" }, { key: "lon", label: "Longitud", type: "number" }]
    : [{ key: "tech", label: "Tecnología", type: "tech" }, { key: "name", label: "Nombre (opcional)" }, { key: "mw", label: "MW", type: "number" }, { key: "bus", label: "Barra (B###)" }];
  return <>
    <h4>{loads ? "Agregar carga o datacenter" : "Agregar generador"}</h4>
    <Form specs={specs} f={add} submit="Agregar" onSubmit={(v) => { delete v.lat; delete v.lon; return p.edit((sid, rev) => addElement(sid, p.kind, v, rev)); }}>
      {loads && <>
        <button type="button" className="btn" onClick={() => p.pick((lon, lat) => add.merge({ lon: lon.toFixed(4), lat: lat.toFixed(4) }))}>Elegir en el mapa</button>
        <button type="button" className="btn" disabled={!add.values.lat || !add.values.lon} onClick={connect}>Conectar a la subestación ≥220 kV más cercana</button>
      </>}
    </Form>
    {near && <p className="meta">{near}</p>}
    <p className="meta">{loads ? "La carga se conecta a una barra existente; la ubicación solo sirve para elegirla." : "Hidro, térmica, bioenergía y geotérmica son sincrónicas y aportan inercia (H = 4 s, supuesto)."} El desbalance se redespacha en la isla (supuesto).</p>
    <h4>{loads ? "Cargas de la sesión" : "Generadores de la sesión"} · {rows.length}</h4>
    {rows.length === 0 && <p className="meta">Ninguno todavía.</p>}
    {rows.map((x) => <Row key={x.id} id={x.id} kind={p.kind} edit={p.edit} origin="session" assumption inService={x.in_service !== false}
      title={`${x.id} · ${x.name ?? (loads ? x.kind : x.tech)}`} detail={`${fmt(x.mw)} MW · ${loads ? (x.kind === "datacenter" ? "datacenter" : "consumo") : x.tech} · barra ${x.bus}`}
      specs={loads ? [{ key: "mw", label: "MW", type: "number" }, { key: "name", label: "Nombre" }, { key: "kind", label: "Tipo", type: "kind" }] : [{ key: "mw", label: "MW", type: "number" }, { key: "name", label: "Nombre" }, { key: "tech", label: "Tecnología", type: "tech" }]}
      init={loads ? { mw: String(x.mw), name: x.name ?? "", kind: x.kind ?? "datacenter" } : { mw: String(x.mw), name: x.name ?? "", tech: x.tech ?? "solar" }} />)}
  </>;
}

/** One element: summary line, origin tag and, when opened, a patch form plus service and delete buttons. */
function Row(p: { id: string; kind: Kind; edit: Edit; origin?: string; assumption?: boolean; inService: boolean; title: string; detail: string; specs: Spec[]; init: Values; kvs?: number[] }) {
  const [open, setOpen] = useState(false);
  const f = useForm(p.init);
  const session = p.origin === "session";
  return (
    <div className={`data-row${p.inService ? "" : " off"}`}>
      <button className="row-btn" onClick={() => { f.reset(); setOpen(!open); }}>
        <span>{p.title}<br /><span className="meta">{p.detail}</span></span>
        <span className="tags">
          <span className={session ? "tag session" : "tag"}>{session ? "sesión" : "base"}</span>
          {p.assumption && <span className="tag assumption">supuesto (sesión)</span>}
          {!p.inService && <span className="tag off">fuera de servicio</span>}
        </span>
      </button>
      {open && <Form specs={p.specs} kvs={p.kvs} f={f} submit="Guardar" onSubmit={(v) => {
        const changed = Object.fromEntries(Object.entries(v).filter(([k, x]) => String(x) !== p.init[k]));
        if (!Object.keys(changed).length) return Promise.resolve(false);
        return p.edit((sid, rev) => updateElement(sid, p.kind, p.id, changed, rev)).then((ok) => (ok && setOpen(false), ok));
      }}>
        <button type="button" className="btn" onClick={() => p.edit((sid, rev) => updateElement(sid, p.kind, p.id, { in_service: !p.inService }, rev))}>{p.inService ? "Fuera de servicio" : "Poner en servicio"}</button>
        {session && <button type="button" className="btn" onClick={() => p.edit((sid, rev) => deleteElement(sid, p.kind, p.id, rev))}>Borrar</button>}
      </Form>}
    </div>
  );
}
interface FormState { values: Values; merge(v: Values): void; reset(): void }

function useForm(init: Values): FormState {
  const [values, setValues] = useState(init);
  return { values, merge: (v) => setValues((old) => ({ ...old, ...v })), reset: () => setValues(init) };
}

/** Inputs for specs; empty fields are left out, numbers are parsed (comma or dot). */
function Form(p: { specs: Spec[]; f: FormState; submit: string; kvs?: number[]; onSubmit(v: Record<string, string | number>): Promise<boolean>; children?: ReactNode }) {
  const send = async (e: FormEvent) => {
    e.preventDefault();
    const v: Record<string, string | number> = {};
    for (const s of p.specs) {
      const raw = (p.f.values[s.key] ?? "").trim();
      if (raw !== "") v[s.key] = s.type === "number" || s.type === "kv" ? Number(raw.replace(",", ".")) : raw;
    }
    if (await p.onSubmit(v)) p.f.reset();
  };
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => p.f.merge({ [k]: e.target.value });
  return (
    <form className="data-form" onSubmit={send}>
      {p.specs.map((s) => <label key={s.key}><span>{s.label}</span>
        {s.type === "kv" ? <select value={p.f.values[s.key]} onChange={set(s.key)}>{(p.kvs ?? []).map((k) => <option key={k} value={String(k)}>{k} kV</option>)}</select>
          : s.type === "tech" ? <select value={p.f.values[s.key]} onChange={set(s.key)}>{TECHS.map((t) => <option key={t}>{t}</option>)}</select>
          : s.type === "kind" ? <select value={p.f.values[s.key]} onChange={set(s.key)}><option value="datacenter">datacenter</option><option value="consumo">consumo</option></select>
          : <input value={p.f.values[s.key] ?? ""} inputMode={s.type === "number" ? "decimal" : undefined} onChange={set(s.key)} />}
      </label>)}
      <div className="data-actions"><button type="submit" className="btn">{p.submit}</button>{p.children}</div>
    </form>
  );
}

function Filter(p: { value: string; set(v: string): void; count: number }) {
  return <label className="data-filter"><input placeholder="Filtrar por id o nombre" aria-label="Filtrar" value={p.value} onChange={(e) => p.set(e.target.value)} />
    <span className="meta">{p.count > LIMIT ? `${LIMIT} de ${p.count}` : p.count}</span></label>;
}

function _filter<T>(rows: T[], text: string, key: (x: T) => string): T[] {
  const q = text.trim().toLowerCase();
  return q ? rows.filter((x) => key(x).toLowerCase().includes(q)) : [...rows];
}
