import { useId, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from "react";
import { lineName } from "../cascade/text";
import type { SessionNetwork } from "../cascade/types";
import { BUS_MW, CAPACITY_MW, ELEMENT_MW, formErrors, LAT, loadingText, LON, mwText, NAME, parseNumber, X_PU, type Spec } from "./forms";
import { nearestBus } from "./geo";
import { addElement, deleteElement, resetSession, updateElement, type Kind } from "./sessionApi";
import type { Edit } from "./useSession";

type Sub = "buses" | "lines" | "generators" | "loads";
const SUBS: [Sub, string][] = [["buses", "Barras"], ["lines", "Líneas"], ["generators", "Generadores"], ["loads", "Cargas y datacenters"]];
const TECHS = ["solar", "eolica", "hidro", "termica", "bioenergia", "geotermica"];
const LIMIT = 60;
const ASSUMED = "Valor que agregó o cambió esta sesión: no viene de los datos públicos.";
type Values = Record<string, string>;
export type Pick = (onPoint: (lon: number, lat: number) => void) => void;

/**
 * Tab "Datos": the session's editable copy of the 188-bus network. Every value it adds is an assumption. One write at a
 * time: while a change and the reload after it are pending, every control is disabled, so a second edit never goes out
 * with the revision the first one already replaced (a 412 against yourself). Each form checks its fields before sending.
 */
export function DataPanel(p: { network: SessionNetwork; edit: Edit; pick: Pick; picking: boolean }) {
  const [sub, setSub] = useState<Sub>("loads");
  const [pending, setPending] = useState(false);
  const writing = useRef(false);
  const edit: Edit = async (fn) => {
    if (writing.current) return false;
    writing.current = true;
    setPending(true);
    try { return await p.edit(fn); } finally { writing.current = false; setPending(false); }
  };
  const n = p.network;
  const kvs = [...new Set(n.nodes.map((x) => x.kv))].sort((a, b) => a - b);
  const reset = () => { if (confirm("¿Borrar todos los cambios de esta sesión? Afecta a todos sus participantes.")) void edit((sid, rev) => resetSession(sid, rev)); };
  const props = { network: n, edit, pick: p.pick, kvs };
  // The engine marks a line overloaded above 100 %; lines held at their limit read 100,0 %, so they are named as such.
  return (
    <section className="data-panel">
      <div className="card">
        <div className="card-head"><h3>Caso base de la sesión</h3><button className="text-btn" onClick={reset} disabled={pending}>Restablecer</button></div>
        <div className="figures">
          <div className="figure"><b>{loadingText(n.baseline.max_loading)}</b><span>carga máxima de una línea</span></div>
          <div className="figure"><b>{n.baseline.overloaded.length.toLocaleString("es-CL")}</b><span>{n.baseline.max_loading < 1.0005 ? "líneas en su capacidad máxima" : "líneas sobrecargadas"}</span></div>
          <div className="figure"><b>{mwText(n.baseline.load_shed_mw)} MW</b><span>desconectados sin corte</span></div>
        </div>
        {n.balance.map((b, i) => <p key={i} className="meta"><span className="tag assumption" title={ASSUMED}>supuesto (sesión)</span> Redespacho de {mwText(b.redispatch_mw)} MW en {Object.keys(b.buses).length} barras. {b.rule}</p>)}
        {n.warnings.map((w, i) => <p key={i} className="note warn">{w.message}</p>)}
        <p className="meta"><span className="tag assumption">supuesto (sesión)</span> marca un valor que agregó o cambió esta sesión: no viene de los datos públicos.</p>
      </div>
      {p.picking && <p className="meta">Haz clic en el mapa para elegir la ubicación.</p>}
      {pending && <p className="meta" role="status">Guardando el cambio y recargando la sesión…</p>}
      <div className="seg" role="tablist" aria-label="Elementos de la red">
        {SUBS.map(([k, label]) => <button key={k} role="tab" aria-selected={sub === k} className={sub === k ? "on" : ""} onClick={() => setSub(k)}>{label}</button>)}
      </div>
      <fieldset className="data-fieldset" disabled={pending}>
        {sub === "buses" && <Buses {...props} />}
        {sub === "lines" && <Lines {...props} />}
        {sub === "generators" && <Elements {...props} kind="generators" />}
        {sub === "loads" && <Elements {...props} kind="loads" />}
      </fieldset>
    </section>
  );
}
type Props = { network: SessionNetwork; edit: Edit; pick: Pick; kvs: number[] };

const BUS_ADD: Spec[] = [{ key: "name", label: "Nombre", required: true, ...NAME }, { key: "kv", label: "kV", type: "kv", required: true }, { key: "lat", label: "Latitud", type: "number", required: true, ...LAT }, { key: "lon", label: "Longitud", type: "number", required: true, ...LON }];
const BUS_EDIT: Spec[] = [{ key: "name", label: "Nombre", ...NAME }, { key: "kv", label: "kV", type: "kv" }, { key: "load_mw", label: "Demanda MW", type: "number", ...BUS_MW }, { key: "gen_mw", label: "Generación MW", type: "number", ...BUS_MW }, { key: "sync_mw", label: "Sincrónica MW", type: "number", ...BUS_MW }, { key: "inertia_mws", label: "Inercia MWs", type: "number", min: 0, max: 200000 }];
const LINE_ADD: Spec[] = [{ key: "a", label: "Barra A (B###)", required: true, bus: true }, { key: "b", label: "Barra B (B###)", required: true, bus: true }, { key: "kv", label: "kV", type: "kv", required: true }, { key: "capacity_mw", label: "Capacidad MW", type: "number", required: true, ...CAPACITY_MW }, { key: "name", label: "Nombre (opcional)", ...NAME }];
const LINE_EDIT: Spec[] = [{ key: "capacity_mw", label: "Capacidad MW", type: "number", ...CAPACITY_MW }, { key: "x_pu", label: "Reactancia (pu)", type: "number", ...X_PU }];

function Buses(p: Props) {
  const [filter, setFilter] = useState("");
  const add = useForm({ name: "", kv: "220", lat: "", lon: "" });
  const rows = _filter(p.network.nodes, filter, (x) => `${x.id} ${x.name}`).sort((a, b) => Number(b.origin === "session") - Number(a.origin === "session"));
  return <>
    <h4>Agregar barra (subestación nueva)</h4>
    <Form specs={BUS_ADD} kvs={p.kvs} f={add} submit="Agregar barra" onSubmit={(v) => p.edit((sid, rev) => addElement(sid, "buses", v, rev))}>
      <button type="button" className="secondary-btn" onClick={() => p.pick((lon, lat) => add.merge({ lon: lon.toFixed(4), lat: lat.toFixed(4) }))}>Elegir en el mapa</button>
    </Form>
    <p className="meta">Una barra nueva queda aislada hasta que le agregues una línea (pestaña Líneas).</p>
    <Filter value={filter} set={setFilter} count={rows.length} />
    {rows.slice(0, LIMIT).map((x) => {
      const b = p.network.buses[x.id];
      return <Row key={x.id} id={x.id} kind="buses" edit={p.edit} origin={x.origin} assumption={x.is_assumption} inService={x.in_service !== false} kvs={p.kvs}
        title={`${x.name} · ${Math.round(x.kv)} kV`} detail={`${mwText(b?.load_mw ?? 0)} MW demanda · ${mwText(b?.gen_mw ?? 0)} MW generación`}
        specs={BUS_EDIT} init={{ name: x.name, kv: String(x.kv), load_mw: String(b?.load_mw ?? ""), gen_mw: String(b?.gen_mw ?? ""), sync_mw: "", inertia_mws: "" }} />;
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
    <Form specs={LINE_ADD} kvs={p.kvs} f={add} submit="Agregar línea" onSubmit={(v) => p.edit((sid, rev) => addElement(sid, "lines", v, rev))} />
    <p className="meta">La reactancia se estima con el largo y la tensión de la línea (supuesto).</p>
    {net.out_of_service.lines.length > 0 && <>
      <h4>Fuera de servicio · {net.out_of_service.lines.length}</h4>
      {net.out_of_service.lines.map((id) => <div className="data-line" key={id}><span>{lineName(net, id)}</span><button className="text-btn" onClick={() => p.edit((sid, rev) => updateElement(sid, "lines", id, { in_service: true }, rev))}>Poner en servicio</button></div>)}
    </>}
    <Filter value={filter} set={setFilter} count={rows.length} />
    {rows.slice(0, LIMIT).map((l) => <Row key={l.id} id={l.id} kind="lines" edit={p.edit} origin={l.origin} assumption={l.is_assumption} inService
      title={`${l.id} · ${lineName(net, l.id)}`} detail={`${mwText(l.capacity_mw)} MW de capacidad`}
      specs={LINE_EDIT} init={{ capacity_mw: String(l.capacity_mw), x_pu: String(l.x_pu) }} />)}
  </>;
}

function Elements(p: Props & { kind: "loads" | "generators" }) {
  const loads = p.kind === "loads";
  const add = useForm(loads ? { kind: "datacenter", name: "", mw: "", bus: "", lat: "", lon: "" } : { tech: "solar", name: "", mw: "", bus: "" });
  const [near, setNear] = useState<string | null>(null);
  const lat = parseNumber(add.values.lat ?? ""), lon = parseNumber(add.values.lon ?? "");
  const connect = () => {
    const best = nearestBus(p.network.nodes, lon, lat, 220);
    if (best) { add.merge({ bus: best.node.id }); setNear(`${best.node.id} · ${best.node.name} (${Math.round(best.node.kv)} kV) a ${best.km.toLocaleString("es-CL", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} km`); }
    else setNear("No hay subestaciones de 220 kV o más en servicio.");
  };
  const rows = loads ? p.network.loads : p.network.generators;
  const specs: Spec[] = loads
    ? [{ key: "kind", label: "Tipo", type: "kind" }, { key: "name", label: "Nombre", required: true, ...NAME }, { key: "mw", label: "MW", type: "number", required: true, ...ELEMENT_MW }, { key: "bus", label: "Barra (B###)", required: true, bus: true }, { key: "lat", label: "Latitud", type: "number", ...LAT }, { key: "lon", label: "Longitud", type: "number", ...LON }]
    : [{ key: "tech", label: "Tecnología", type: "tech" }, { key: "name", label: "Nombre (opcional)", ...NAME }, { key: "mw", label: "MW", type: "number", required: true, ...ELEMENT_MW }, { key: "bus", label: "Barra (B###)", required: true, bus: true }];
  const editSpecs: Spec[] = loads
    ? [{ key: "mw", label: "MW", type: "number", ...ELEMENT_MW }, { key: "name", label: "Nombre", ...NAME }, { key: "kind", label: "Tipo", type: "kind" }]
    : [{ key: "mw", label: "MW", type: "number", ...ELEMENT_MW }, { key: "name", label: "Nombre", ...NAME }, { key: "tech", label: "Tecnología", type: "tech" }];
  return <>
    <h4>{loads ? "Agregar carga o datacenter" : "Agregar generador"}</h4>
    <Form specs={specs} f={add} submit="Agregar" onSubmit={(v) => { delete v.lat; delete v.lon; return p.edit((sid, rev) => addElement(sid, p.kind, v, rev)); }}>
      {loads && <>
        <button type="button" className="secondary-btn" onClick={() => p.pick((x, y) => add.merge({ lon: x.toFixed(4), lat: y.toFixed(4) }))}>Elegir en el mapa</button>
        <button type="button" className="secondary-btn" disabled={!Number.isFinite(lat) || !Number.isFinite(lon)} onClick={connect}>Conectar a la subestación ≥220 kV más cercana</button>
      </>}
    </Form>
    {near && <p className="meta">{near}</p>}
    <p className="meta">{loads ? "La carga se conecta a una barra existente; la ubicación solo sirve para elegirla." : "Hidro, térmica, bioenergía y geotérmica son sincrónicas y aportan inercia (H = 4 s, supuesto)."} El desbalance se redespacha en la isla (supuesto).</p>
    <h4>{loads ? "Cargas de la sesión" : "Generadores de la sesión"} · {rows.length}</h4>
    {rows.length === 0 && <p className="meta">Ninguno todavía.</p>}
    {rows.map((x) => <Row key={x.id} id={x.id} kind={p.kind} edit={p.edit} origin="session" assumption inService={x.in_service !== false}
      title={`${x.id} · ${x.name ?? (loads ? x.kind : x.tech)}`} detail={`${mwText(x.mw)} MW · ${loads ? (x.kind === "datacenter" ? "datacenter" : "consumo") : x.tech} · barra ${x.bus}`}
      specs={editSpecs} init={loads ? { mw: String(x.mw), name: x.name ?? "", kind: x.kind ?? "datacenter" } : { mw: String(x.mw), name: x.name ?? "", tech: x.tech ?? "solar" }} />)}
  </>;
}

/** One element: summary line, origin tag and, when opened, a patch form plus service and delete buttons. */
function Row(p: { id: string; kind: Kind; edit: Edit; origin?: string; assumption?: boolean; inService: boolean; title: string; detail: string; specs: Spec[]; init: Values; kvs?: number[] }) {
  const [open, setOpen] = useState(false);
  const f = useForm(p.init);
  const session = p.origin === "session";
  return (
    <div className={`data-row${p.inService ? "" : " off"}`}>
      <button type="button" className="row-btn" aria-expanded={open} onClick={() => { f.reset(); setOpen(!open); }}>
        <span>{p.title}<br /><span className="meta">{p.detail}</span></span>
        <span className="tags">
          <span className={session ? "tag session" : "tag"}>{session ? "sesión" : "base"}</span>
          {p.assumption && <span className="tag assumption" title={ASSUMED}>supuesto (sesión)</span>}
          {!p.inService && <span className="tag off">fuera de servicio</span>}
        </span>
      </button>
      {open && <Form specs={p.specs} kvs={p.kvs} f={f} submit="Guardar" onSubmit={(v) => {
        const changed = Object.fromEntries(Object.entries(v).filter(([k, x]) => String(x) !== p.init[k]));
        if (!Object.keys(changed).length) return Promise.resolve(false);
        return p.edit((sid, rev) => updateElement(sid, p.kind, p.id, changed, rev)).then((ok) => (ok && setOpen(false), ok));
      }}>
        <button type="button" className="secondary-btn" onClick={() => p.edit((sid, rev) => updateElement(sid, p.kind, p.id, { in_service: !p.inService }, rev))}>{p.inService ? "Fuera de servicio" : "Poner en servicio"}</button>
        {session && <button type="button" className="secondary-btn" onClick={() => p.edit((sid, rev) => deleteElement(sid, p.kind, p.id, rev))}>Borrar</button>}
      </Form>}
    </div>
  );
}
interface FormState { values: Values; merge(v: Values): void; reset(): void }

function useForm(init: Values): FormState {
  const [values, setValues] = useState(init);
  return { values, merge: (v) => setValues((old) => ({ ...old, ...v })), reset: () => setValues(init) };
}

/**
 * Inputs for specs. Sending checks every field first and shows each error next to its field; nothing goes out while
 * one is wrong. Empty fields are left out; numbers are parsed with a decimal comma or dot.
 */
function Form(p: { specs: Spec[]; f: FormState; submit: string; kvs?: number[]; onSubmit(v: Record<string, string | number>): Promise<boolean>; children?: ReactNode }) {
  const [errors, setErrors] = useState<Record<string, string>>({});
  const id = useId();
  const send = async (e: FormEvent) => {
    e.preventDefault();
    const bad = formErrors(p.specs, p.f.values);
    setErrors(bad);
    if (Object.keys(bad).length) return;
    const v: Record<string, string | number> = {};
    for (const s of p.specs) {
      const raw = (p.f.values[s.key] ?? "").trim();
      if (raw !== "") v[s.key] = s.type === "number" || s.type === "kv" ? parseNumber(raw) : raw;
    }
    if (await p.onSubmit(v)) p.f.reset();
  };
  const set = (k: string) => (e: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    p.f.merge({ [k]: e.target.value });
    if (errors[k]) setErrors((x) => { const n = { ...x }; delete n[k]; return n; });
  };
  return (
    <form className="data-form" onSubmit={send} noValidate>
      {p.specs.map((s) => {
        const err = errors[s.key];
        const fid = `${id}-${s.key}`;
        const aria = { id: fid, "aria-invalid": err ? true : undefined, "aria-describedby": err ? `${fid}-err` : undefined };
        return <label key={s.key} className={err ? "bad" : undefined}><span>{s.label}</span>
          {s.type === "kv" ? <select {...aria} value={p.f.values[s.key]} onChange={set(s.key)}>{(p.kvs ?? []).map((k) => <option key={k} value={String(k)}>{k} kV</option>)}</select>
            : s.type === "tech" ? <select {...aria} value={p.f.values[s.key]} onChange={set(s.key)}>{TECHS.map((t) => <option key={t}>{t}</option>)}</select>
            : s.type === "kind" ? <select {...aria} value={p.f.values[s.key]} onChange={set(s.key)}><option value="datacenter">datacenter</option><option value="consumo">consumo</option></select>
            : <input {...aria} value={p.f.values[s.key] ?? ""} inputMode={s.type === "number" ? "decimal" : undefined} onChange={set(s.key)} />}
          {err && <span className="data-error" id={`${fid}-err`}>{err}</span>}
        </label>;
      })}
      <div className="data-actions"><button type="submit" className="primary-btn">{p.submit}</button>{p.children}</div>
    </form>
  );
}

function Filter(p: { value: string; set(v: string): void; count: number }) {
  const id = useId();
  return <div className="data-filter">
    <label htmlFor={id}>Filtrar por id o nombre</label>
    <div className="data-filter-row">
      <input id={id} placeholder="Por ejemplo: B010 o Quillota" value={p.value} onChange={(e) => p.set(e.target.value)} />
      <span className="meta">{p.count > LIMIT ? `${LIMIT} de ${p.count}` : p.count}</span>
    </div>
  </div>;
}

function _filter<T>(rows: T[], text: string, key: (x: T) => string): T[] {
  const q = text.trim().toLowerCase();
  return q ? rows.filter((x) => key(x).toLowerCase().includes(q)) : [...rows];
}
