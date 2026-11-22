import { lineName } from "../cascade/text";
import type { Network } from "../cascade/types";

/** Sandbox cut of a session (Simulación tab): the lines open for everyone in it, each with its repair button. */
export function SessionCut(p: { network: Network; open: string[]; notice: string; repair(lines?: string[]): void }) {
  return (
    <div className="card">
      <div className="card-head">
        <h3>Líneas abiertas en la sesión · {p.open.length}</h3>
        {p.open.length > 0 && <button className="text-btn" onClick={() => p.repair()}>Reparar todo</button>}
      </div>
      {p.open.map((id) => <div className="data-line" key={id}><span>{lineName(p.network, id)}</span><button className="text-btn" onClick={() => p.repair([id])}>Reparar</button></div>)}
      <p className="meta">{p.notice}</p>
    </div>
  );
}
