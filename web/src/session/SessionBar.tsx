import { useState } from "react";
import type { Session } from "./useSession";

/**
 * Create, join and leave a shared session (docs/mapa3.md section 11). `compact` is the strip in the panel head
 * (session only): the session's name, its revision and live mode, and **Salir de la sesión**, which goes back to the
 * plain map. There is no share link: `?sesion=` is not read when the page loads, so a copied link would open the plain
 * map. Without `compact`, the card of the "Sesión compartida" view.
 */
export function SessionBar({ s, compact }: { s: Session; compact?: boolean }) {
  const [joining, setJoining] = useState(false);
  const [text, setText] = useState("");
  const label = s.sid ? `Sesión ${s.session?.label ?? s.sid.slice(0, 6)}` : "";
  const name = s.sid && <span className="session-name" title={label}>{label}</span>;
  // The revision counts the saved changes; it says something in the session card, not in the strip (WP2 hand-over).
  const revision = !compact && s.session ? <span className="tag" title="Número de cambios guardados en la sesión">revisión {s.session.revision}</span> : null;
  const tags = <>
    {revision}
    {s.live && <span className={`tag ${s.live === "sse" ? "live" : "poll"}`} title={s.live === "sse" ? "Recibe los cambios al instante" : "Consulta la sesión cada 2 s"}>{s.live === "sse" ? "en vivo" : "sondeo"}</span>}
  </>;
  if (compact) return s.sid ? (
    <div className="session-strip">{name}{tags}<button className="text-btn" onClick={s.leave}>Salir de la sesión</button></div>
  ) : null;
  return (
    <div className="card">
      <div className="card-head"><h3>Sesión compartida</h3></div>
      <p className="meta">Una copia editable de la red: los cambios se ven en vivo para todos sus participantes y la sesión expira 24 h después del último cambio. El caso base no cambia.</p>
      {s.sid ? (
        <div className="session-actions">
          {name}{tags}
          <button className="secondary-btn" onClick={s.leave}>Salir de la sesión</button>
        </div>
      ) : joining ? (
        <form className="session-join" onSubmit={(e) => { e.preventDefault(); s.join(text); setJoining(false); setText(""); }}>
          <input aria-label="Id o enlace de la sesión" placeholder="Id o enlace de la sesión" value={text} onChange={(e) => setText(e.target.value)} autoFocus />
          <button type="submit" className="secondary-btn">Unirse</button><button type="button" className="text-btn" onClick={() => setJoining(false)}>Cancelar</button>
        </form>
      ) : (
        <div className="session-actions">
          <button className="secondary-btn" onClick={() => s.create()}>Crear sesión</button>
          <button className="secondary-btn" onClick={() => setJoining(true)}>Unirse</button>
        </div>
      )}
    </div>
  );
}
