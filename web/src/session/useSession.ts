import { useCallback, useEffect, useRef, useState } from "react";
import type { SessionNetwork } from "../cascade/types";
import { ApiError, createSession, getNetwork, getSession, getState, sessionIdFrom, subscribe, type CutState, type LiveMode, type SessionDoc } from "./sessionApi";

const KEY = "sub50_session";
export type Edit = (fn: (sid: string, revision: number) => Promise<unknown>) => Promise<boolean>;
export interface Session {
  sid: string | null; session: SessionDoc | null; network: SessionNetwork | null; state: CutState | null;
  live: LiveMode | null; error: string | null;
  create(): Promise<void>; join(text: string): void; leave(): void; refresh(): Promise<void>; edit: Edit; clearError(): void;
}

/**
 * Shared session of mapa 3: id from ?sesion= or localStorage, data from the API. A revision event that changed the
 * dataset (dataset_revision) refetches session, network and state; run activity refetches only the session document.
 */
export function useSession(): Session {
  const [sid, setSid] = useState(() => sessionIdFrom(location.search, localStorage.getItem(KEY)));
  const [session, setSession] = useState<SessionDoc | null>(null);
  const [network, setNetwork] = useState<SessionNetwork | null>(null);
  const [state, setState] = useState<CutState | null>(null);
  const [live, setLive] = useState<LiveMode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const loaded = useRef(-1);  // revision of the session on screen
  const data = useRef(-1);    // dataset_revision of the network on screen
  const seq = useRef(0);      // only the newest full refresh is applied
  const docSeq = useRef(0);   // only the newest document read is applied
  const load = useCallback(async (id: string) => {
    const mine = ++seq.current, mineDoc = ++docSeq.current;
    const [doc, net, st] = await Promise.all([getSession(id), getNetwork(id), getState(id)]);
    if (mine !== seq.current || mineDoc !== docSeq.current) return;
    loaded.current = doc.revision; data.current = net.dataset_revision;
    setSession(doc); setNetwork(net); setState(st);
  }, []);
  const loadDoc = useCallback(async (id: string) => {
    const mine = ++docSeq.current;
    const doc = await getSession(id);
    if (mine !== docSeq.current) return;
    loaded.current = doc.revision;
    setSession(doc);
  }, []);
  const leave = useCallback(() => {
    localStorage.removeItem(KEY);
    _setUrl(null);
    seq.current++; docSeq.current++; loaded.current = -1; data.current = -1;
    setSid(null); setSession(null); setNetwork(null); setState(null); setLive(null);
  }, []);
  useEffect(() => {
    if (!sid) return;
    let alive = true;
    localStorage.setItem(KEY, sid);
    _setUrl(sid);
    load(sid).catch((e) => {
      if (!alive) return;
      if (e instanceof ApiError && e.status === 404) { leave(); setError("La sesión no existe o expiró (24 h sin cambios). Se volvió al caso base."); }
      else { setSid(null); setError(`No se pudo conectar con el servidor de sesiones: ${e.message}. Se muestra el caso base.`); }
    });
    const sub = subscribe(sid, (e) => {
      if (!alive || e.revision === loaded.current) return;
      (e.dataset_revision === data.current ? loadDoc(sid) : load(sid)).catch((err) => setError(err.message));
    }, {
      onMode: (m) => alive && setLive(m),
      onGone: () => { if (alive) { leave(); setError("La sesión fue borrada o expiró."); } },
    });
    return () => { alive = false; sub.close(); };
  }, [sid, load, loadDoc, leave]);
  const edit: Edit = useCallback(async (fn) => {
    if (!sid || !network) return false;
    try {
      await fn(sid, network.dataset_revision);
      setError(null);
      await load(sid);
      return true;
    } catch (e) {
      if (e instanceof ApiError && e.status === 412) {
        setError("Otro cliente cambió la sesión antes que tú. Se recargó: revisa y vuelve a intentarlo.");
        await load(sid).catch(() => undefined);
      } else setError((e as Error).message);
      return false;
    }
  }, [sid, network, load]);
  return {
    sid, session, network, state, live, error,
    create: async () => {
      try { const doc = await createSession(); setError(null); setSid(doc.session_id); } catch (e) { setError((e as Error).message); }
    },
    join: (text) => {
      const id = sessionIdFrom(`?sesion=${encodeURIComponent(text.match(/sesion=([^&\s]+)/)?.[1] ?? text.trim())}`, null);
      if (id) { setError(null); setSid(id); } else setError("Ese no es un id de sesión (22 caracteres) ni un enlace con ?sesion=.");
    },
    leave,
    refresh: () => (sid ? load(sid) : Promise.resolve()),
    edit,
    clearError: () => setError(null),
  };
}

function _setUrl(sid: string | null) {
  const url = new URL(location.href);
  if (sid) url.searchParams.set("sesion", sid); else url.searchParams.delete("sesion");
  history.replaceState(null, "", url);
}
