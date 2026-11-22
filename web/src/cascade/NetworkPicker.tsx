import { useEffect, useRef, useState } from "react";
import type { NetworkInfo } from "../map/country";
import { Chevron } from "./ui";

/**
 * The panel header names the network on the map and opens the list of networks (issue #49): the built-in countries,
 * the networks uploaded in this browser (each with "Quitar") and "Subir una red…". Only one network is drawn at a time.
 * Names of uploaded networks are plain text (React escapes them). `locked` (the tip) pins Chile in a shared session.
 */
export function NetworkPicker({ current, networks, choose, remove, upload, locked }: {
  current: NetworkInfo; networks: NetworkInfo[]; choose(id: string): void; remove(id: string): void; upload(): void; locked?: string;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); setOpen(false); } };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", esc, true);
    return () => { document.removeEventListener("pointerdown", close); document.removeEventListener("keydown", esc, true); };
  }, [open]);

  const pick = (id: string) => { setOpen(false); if (id !== current.id) choose(id); };
  const builtIn = networks.filter((n) => !n.uploaded);
  const uploaded = networks.filter((n) => n.uploaded);
  return (
    <div className="crumbs picker" ref={root}>
      <h1>
        <button className="picker-btn" aria-haspopup="true" aria-expanded={open} aria-disabled={locked ? "true" : undefined} data-tip={locked}
          title={current.uploaded ? current.name : undefined} onClick={() => !locked && setOpen(!open)}>
          <span className="ellipsis">{current.name}</span>
          {!locked && <Chevron color="currentColor" />}
        </button>
      </h1>
      <span className="ellipsis">{current.system}</span>
      {open && (
        <div className="picker-pop" role="menu" aria-label="Red en el mapa">
          <h3>Países</h3>
          {builtIn.map((n) => (
            <button key={n.id} role="menuitemradio" aria-checked={n.id === current.id} className={n.id === current.id ? "picker-item on" : "picker-item"} onClick={() => pick(n.id)}>
              <span className="ellipsis">{n.name}</span><span className="picker-meta">{n.simulable ? "simulación" : "solo para ver"}</span>
            </button>
          ))}
          {uploaded.length > 0 && <h3>Redes subidas</h3>}
          {uploaded.map((n) => (
            <div key={n.id} className="picker-row">
              <button role="menuitemradio" aria-checked={n.id === current.id} className={n.id === current.id ? "picker-item on" : "picker-item"} title={n.name} onClick={() => pick(n.id)}>
                <span className="ellipsis">{n.name}</span><span className="picker-meta">{n.country}</span>
              </button>
              <button className="text-btn" aria-label={`Quitar la red ${n.name}`} onClick={() => remove(n.id)}>Quitar</button>
            </div>
          ))}
          <button className="picker-item upload" role="menuitem" onClick={() => { setOpen(false); upload(); }}>Subir una red…</button>
        </div>
      )}
    </div>
  );
}
