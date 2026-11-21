import { useState } from "react";
import type { Session } from "./useSession";

/** Create, join, share and leave a shared session (docs/mapa3.md section 11). */
export function SessionBar({ s }: { s: Session }) {
  const [joining, setJoining] = useState(false);
  const [text, setText] = useState("");
  const [copied, setCopied] = useState(false);
  if (!s.sid) return (
    <div className="session-bar">
      {joining ? (
        <form className="session-join" onSubmit={(e) => { e.preventDefault(); s.join(text); setJoining(false); setText(""); }}>
          <input aria-label="Id o enlace de la sesión" placeholder="Id o enlace de la sesión" value={text} onChange={(e) => setText(e.target.value)} autoFocus />
          <button type="submit">Unirse</button><button type="button" className="link" onClick={() => setJoining(false)}>Cancelar</button>
        </form>
      ) : <>
        <span className="muted">Caso base (sin sesión)</span>
        <button onClick={() => s.create()}>Crear sesión</button>
        <button onClick={() => setJoining(true)}>Unirse</button>
      </>}
    </div>
  );
  const copy = () => {
    if (!s.session) return;
    navigator.clipboard.writeText(`${location.origin}${s.session.share_path}`).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); });
  };
  return (
    <div className="session-bar on">
      <span title={s.sid}>Sesión {s.session?.label ?? s.sid.slice(0, 6)}</span>
      {s.session && <span className="badge">rev. {s.session.revision}</span>}
      {s.live && <span className={`badge ${s.live}`} title={s.live === "sse" ? "Cambios recibidos por SSE" : "Consulta la sesión cada 2 s"}>{s.live === "sse" ? "en vivo" : "sondeo"}</span>}
      <button onClick={copy} disabled={!s.session}>{copied ? "Copiado" : "Copiar enlace"}</button>
      <button onClick={s.leave}>Salir</button>
    </div>
  );
}
