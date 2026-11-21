import { useState } from "react";
import type { Session } from "./useSession";

/**
 * Create, join, share and leave a shared session (docs/mapa3.md section 11). `compact` is the strip in the panel head
 * (session only); without it, the card of the "Sesión compartida" view.
 */
export function SessionBar({ s, compact }: { s: Session; compact?: boolean }) {
  const [joining, setJoining] = useState(false);
  const [text, setText] = useState("");
  const [copied, setCopied] = useState(false);
  const copy = () => {
    if (!s.session) return;
    navigator.clipboard.writeText(`${location.origin}${s.session.share_path}`).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); });
  };
  const name = s.sid && <span title={s.sid}>Sesión {s.session?.label ?? s.sid.slice(0, 6)}</span>;
  const tags = <>
    {s.session && <span className="tag">rev. {s.session.revision}</span>}
    {s.live && <span className={`tag ${s.live === "sse" ? "live" : "poll"}`} title={s.live === "sse" ? "Cambios recibidos por SSE" : "Consulta la sesión cada 2 s"}>{s.live === "sse" ? "en vivo" : "sondeo"}</span>}
  </>;
  const copyLabel = copied ? "Copiado" : "Copiar enlace";
  if (compact) return s.sid ? (
    <div className="session-strip">{name}{tags}<button className="text-btn" onClick={copy} disabled={!s.session}>{copyLabel}</button></div>
  ) : null;
  return (
    <div className="card">
      <div className="card-head"><h3>Sesión compartida</h3></div>
      <p className="meta">Una copia editable de la red que se comparte con un enlace: los cambios se ven en vivo para todos y la sesión expira 24 h después del último cambio. El caso base no cambia.</p>
      {s.sid ? (
        <div className="session-actions">
          {name}{tags}
          <button className="btn" onClick={copy} disabled={!s.session}>{copyLabel}</button>
          <button className="btn" onClick={s.leave}>Salir</button>
        </div>
      ) : joining ? (
        <form className="session-join" onSubmit={(e) => { e.preventDefault(); s.join(text); setJoining(false); setText(""); }}>
          <input aria-label="Id o enlace de la sesión" placeholder="Id o enlace de la sesión" value={text} onChange={(e) => setText(e.target.value)} autoFocus />
          <button type="submit" className="btn">Unirse</button><button type="button" className="text-btn" onClick={() => setJoining(false)}>Cancelar</button>
        </form>
      ) : (
        <div className="session-actions">
          <button className="btn" onClick={() => s.create()}>Crear sesión</button>
          <button className="btn" onClick={() => setJoining(true)}>Unirse</button>
        </div>
      )}
    </div>
  );
}
