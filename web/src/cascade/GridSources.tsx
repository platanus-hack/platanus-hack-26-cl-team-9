import { useEffect, useState } from "react";
import { int } from "./text";
import { loadCatalog, type Catalog } from "./gridsApi";
import { Chevron } from "./ui";

const KB = (bytes: number) => `${Math.max(1, Math.round(bytes / 1024))} KB`;

/**
 * "Fuentes de la grilla": one collapsible row per country with a checkbox. Chile is the simulable network and cannot
 * be removed; the other countries are context that is only drawn. Ticking a country recomposes the grid at once.
 * The scenario and operating point come from the rail's "Escenarios".
 */
export function GridSources({ composed, busy, apply, reset, locked }: {
  composed: string | null; busy: boolean; apply(contextKeys: string[]): void; reset(): void; locked: boolean;
}) {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string> | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadCatalog().then((c) => { setCatalog(c); setChecked(new Set(c.context.map((d) => d.key))); }).catch((e) => setError(String(e.message)));
  }, []);

  if (error) return <p className="note">{error}</p>;
  if (!catalog || !checked) return <p className="meta">Leyendo el catálogo…</p>;

  const expand = (id: string) => setOpen((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const tick = (key: string) => {
    const next = new Set(checked);
    if (next.has(key)) next.delete(key); else next.add(key);
    setChecked(next);
    apply(catalog.context.map((d) => d.key).filter((k) => next.has(k)));
  };
  const chile = catalog.documents.filter((d) => d.country === "CHL" && d.role !== "scenario");

  return (
    <div className="grid-sources">
      {locked && <p className="note">En una sesión compartida la grilla está fija. Sal de la sesión para elegir fuentes.</p>}
      <p className="meta">Elige qué países arman la grilla. El escenario y la hora se eligen en Escenarios.</p>
      <ul className="source-tree">
        <li>
          <div className="source-row">
            <button className="disclosure" aria-expanded={open.has("CHL")} aria-label="Detalle de Chile" onClick={() => expand("CHL")}><Chevron dir={open.has("CHL") ? "down" : "right"} color="currentColor" /></button>
            <label className="check" title="Es la red simulable: no se puede quitar"><input type="checkbox" checked disabled /><span>Chile<em> · red simulable</em></span></label>
          </div>
          {open.has("CHL") && <ul className="source-docs">{chile.map((d) => <li key={d.key}><span>{d.key.replace("CHL/", "")}</span><em>{KB(d.bytes)}</em></li>)}</ul>}
        </li>
        {catalog.context.map((d) => (
          <li key={d.key}>
            <div className="source-row">
              <button className="disclosure" aria-expanded={open.has(d.key)} aria-label={`Detalle de ${d.name}`} onClick={() => expand(d.key)}><Chevron dir={open.has(d.key) ? "down" : "right"} color="currentColor" /></button>
              <label className="check"><input type="checkbox" checked={checked.has(d.key)} disabled={busy || locked} onChange={() => tick(d.key)} /><span>{d.name}<em> · contexto</em></span></label>
            </div>
            {open.has(d.key) && (
              <ul className="source-docs">
                <li><span>Líneas</span><em>{int(d.lines)}</em></li>
                <li><span>Subestaciones</span><em>{int(d.substations)}</em></li>
                <li><span>Centrales</span><em>{int(d.plants)}</em></li>
                <li><span>{d.key}</span><em>{KB(d.bytes)}</em></li>
              </ul>
            )}
          </li>
        ))}
      </ul>
      <div className="source-actions">
        {busy && <span className="meta">Componiendo…</span>}
        {composed && !busy && <button className="text-btn" onClick={() => { reset(); setChecked(new Set(catalog.context.map((d) => d.key))); }}>Volver a la caché</button>}
      </div>
      <p className="source">{composed ? `Grilla compuesta desde S3: ${composed}.` : "Ahora se muestra la caché de la app (web/public/cache)."} Catálogo publicado {catalog.built_at}.</p>
    </div>
  );
}
