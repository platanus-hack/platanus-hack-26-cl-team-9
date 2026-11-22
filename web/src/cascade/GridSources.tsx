import { useEffect, useState } from "react";
import { loadCatalog, type Catalog } from "./gridsApi";
import { Chevron, Icon } from "./ui";

/** A ticked network: its country and the stored context document it is composed from (null for Chile). */
export interface SourcePick { country: string; key: string | null }

/**
 * "Fuentes de la grilla" in the nav rail: opens downward as a list of the networks the backend stores, each with a
 * checkbox and its status (Complete: it can be simulated; Partial: it is only drawn). Tick as many as wanted: with
 * Chile ticked, Chile is the simulated network and the others are drawn around it as context; without Chile, the
 * ticked countries are shown together, view only. Each tick composes the grid at once. The hour comes from "Escenarios".
 */
export function GridSources({ current, composed, busy, apply, reset, locked }: {
  current: string; composed: string | null; busy: boolean; apply(picks: SourcePick[]): void; reset(): void; locked: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checked, setChecked] = useState<Set<string>>(new Set([current]));
  useEffect(() => { if (!composed) setChecked(new Set([current])); }, [current, composed]); // back to the cache: the network on the map

  function toggleOpen() {
    setExpanded(!expanded);
    if (catalog || error) return;
    loadCatalog().then(setCatalog).catch((e) => setError(String(e.message)));
  }
  function tick(country: string) {
    if (!catalog || busy || locked) return;
    const next = new Set(checked);
    if (next.has(country)) next.delete(country); else next.add(country);
    if (next.size === 0) return; // at least one network stays on the map
    setChecked(next);
    apply(catalog.grids.filter((g) => next.has(g.country)).map((g) => ({ country: g.country, key: g.key })));
  }

  return (
    <>
      <button className="rail-item" aria-expanded={expanded} onClick={toggleOpen}>
        <Icon><path d="M2 3.5h5v4H2zM9 3.5h5v4H9zM5.5 9.5h5v4h-5zM4.5 7.5v1M11.5 7.5v1M8 8.5v1" /></Icon><span className="rail-label">Fuentes de la grilla</span>
        <span className="rail-chevron"><Chevron dir={expanded ? "down" : "right"} color="currentColor" /></span>
      </button>
      {expanded && (
        <div className="scenarios sources" role="group" aria-label="Redes de la grilla">
          {error && <p className="source-note">{error}</p>}
          {!error && !catalog && <p className="source-note">Leyendo el catálogo…</p>}
          {catalog?.grids.map((g) => (
            <label className="source-row" key={g.country} title={locked ? "En una sesión compartida la grilla está fija" : undefined}>
              <input type="checkbox" checked={checked.has(g.country)} disabled={busy || locked} onChange={() => tick(g.country)} />
              <span className="ellipsis">{g.name}</span>
              <span className={`source-status ${g.status.toLowerCase()}`}>{g.status}</span>
            </label>
          ))}
          {composed && !busy && !locked && <button className="text-btn source-reset" onClick={reset}>Volver a la caché</button>}
          {busy && <p className="source-note">Componiendo…</p>}
        </div>
      )}
    </>
  );
}
