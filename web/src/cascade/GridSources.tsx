import { useState } from "react";
import { loadCatalog, type Catalog } from "./gridsApi";
import { Chevron, Icon } from "./ui";

/**
 * "Fuentes de la grilla" in the nav rail: opens downward as a list of the networks the backend stores, each with its
 * status (Complete: it can be simulated; Partial: it is only drawn). One network is on the map at a time (issue #49), so a
 * row is a choice, not a tick: choosing it composes that network from the stored documents and shows it alone, the same
 * as choosing it in the panel header. The marked row is the network on the map. The hour comes from "Escenarios".
 */
export function GridSources({ current, composed, busy, apply, reset, locked }: {
  current: string; composed: string | null; busy: boolean; apply(country: string, key: string | null): void; reset(): void; locked: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);

  function toggleOpen() {
    setExpanded(!expanded);
    if (catalog || error) return;
    loadCatalog().then(setCatalog).catch((e) => setError(String(e.message)));
  }
  /** A click on the marked row composes it from the backend when it came from the app files; on a composed one it does nothing. */
  function choose(country: string, key: string | null) {
    if (busy || locked || composed === country) return;
    apply(country, key);
  }

  return (
    <>
      <button className="rail-item" aria-expanded={expanded} onClick={toggleOpen}>
        <Icon><path d="M2 3.5h5v4H2zM9 3.5h5v4H9zM5.5 9.5h5v4h-5zM4.5 7.5v1M11.5 7.5v1M8 8.5v1" /></Icon><span className="rail-label">Fuentes de la grilla</span>
        <span className="rail-chevron"><Chevron dir={expanded ? "down" : "right"} color="currentColor" /></span>
      </button>
      {expanded && (
        <div className="scenarios sources" role="radiogroup" aria-label="Red de la grilla">
          {error && <p className="source-note">{error}</p>}
          {!error && !catalog && <p className="source-note">Leyendo el catálogo…</p>}
          {catalog?.grids.map((g) => (
            <label className="source-row" key={g.country} title={locked ? "En una sesión compartida la grilla está fija" : undefined}>
              <input type="radio" name="grid-source" checked={current === g.country} disabled={busy || locked} onChange={() => choose(g.country, g.key)} onClick={() => current === g.country && choose(g.country, g.key)} />
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
