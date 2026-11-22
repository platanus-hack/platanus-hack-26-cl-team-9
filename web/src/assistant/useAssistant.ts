import { useCallback, useEffect, useRef, useState } from "react";
import { getRunSnapshots } from "../session/sessionApi";
import type { Session } from "../session/useSession";
import { AssistantError, deleteConversation, getConversation, MAX_MESSAGE, streamChat } from "./assistantApi";
import { refreshFor } from "./labels";
import type { SseEvent } from "./sse";
import { annotate, begin, EMPTY, fail, fromConversation, interrupt, reduce, type ChatState } from "./steps";

export const CID_KEY = "sub50.assistant.cid";
const REFRESH_MS = 300;
const RECOVER_TRIES = 5;
const RECOVER_MS = 3000;

export interface Assistant {
  state: ChatState; busy: boolean; enabled: boolean; restoring: boolean;
  send(text: string): Promise<void>; reset(): Promise<void>;
}

/**
 * State of the assistant chat, owned by CascadeApp so it survives view changes (docs/assistant.md section 2c). The map
 * follows the assistant: a `session_id` in the stream that differs from the one on screen joins it, and each tool
 * result reloads the session (network and cut state); after `step` the run snapshots are fetched and summarised in
 * the card. The conversation id is kept in localStorage and the chat is rebuilt from `GET /conversations/{cid}`.
 */
export function useAssistant(s: Session): Assistant {
  const [state, setState] = useState<ChatState>(EMPTY);
  const [busy, setBusy] = useState(false);
  const [enabled, setEnabled] = useState(true);
  const [restoring, setRestoring] = useState(() => !!readCid());
  const live = useRef({ state, s, busy });
  live.current = { state, s, busy };
  const abort = useRef<AbortController | null>(null);
  const refreshTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // Rehydrate the stored conversation once; a 404 means it expired, so forget it.
  useEffect(() => {
    const cid = readCid();
    if (!cid) return;
    let alive = true;
    getConversation(cid).then((view) => {
      if (!alive) return;
      setState(fromConversation(view));
      if (view.session_id && !live.current.s.sid) live.current.s.join(view.session_id);
    }, (e) => {
      if (!alive) return;
      if (e instanceof AssistantError && e.status === 404) writeCid(null);
      if (e instanceof AssistantError && e.status === 503) setEnabled(false);
    }).finally(() => alive && setRestoring(false));
    return () => { alive = false; };
  }, []);
  useEffect(() => { if (state.conversationId) writeCid(state.conversationId); }, [state.conversationId]);
  useEffect(() => () => { abort.current?.abort(); clearTimeout(refreshTimer.current); }, []);

  /** Join the session the assistant works on when it is not the one on screen; true when it joined. */
  const follow = useCallback((sid: unknown) => {
    const cur = live.current.s;
    if (typeof sid !== "string" || !sid || sid === cur.sid) return false;
    cur.join(sid);
    return true;
  }, []);

  const onEvent = useCallback((e: SseEvent) => {
    setState((st) => reduce(st, e));
    const d = (e.data ?? {}) as Record<string, unknown>;
    if (e.event === "start" || e.event === "done") { follow(d.session_id); return; }
    if (e.event !== "tool_result") return;
    const joined = follow(d.session_id);
    const what = refreshFor(typeof d.name === "string" ? d.name : "");
    if (!d.ok || !what) return;
    // The session SSE reports the change too; this reload is the fallback (a joined session loads by itself).
    if (!joined) {
      clearTimeout(refreshTimer.current);
      refreshTimer.current = setTimeout(() => { live.current.s.refresh().catch(() => undefined); }, REFRESH_MS);
    }
    if (what === "snapshots" && typeof d.session_id === "string" && typeof d.run_id === "string") {
      const id = typeof d.id === "string" ? d.id : "";
      void summariseSnapshots(d.session_id, d.run_id, d.result).then((text) => text && setState((st) => annotate(st, id, text)));
    }
  }, [follow]);

  const send = useCallback(async (raw: string) => {
    const text = raw.trim();
    if (!text || text.length > MAX_MESSAGE || live.current.busy) return;
    const { state: st, s: sess } = live.current;
    setBusy(true);
    setState((x) => begin(x, text));
    const ctrl = new AbortController();
    abort.current = ctrl;
    try {
      const finished = await streamChat({ message: text, conversation_id: st.conversationId ?? undefined, session_id: sess.sid ?? undefined }, onEvent, ctrl.signal);
      if (!finished) await recover();
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      const err = e instanceof AssistantError ? e : new AssistantError(0);
      if (err.status === 503) setEnabled(false);
      if (err.status === 404) { writeCid(null); setState((x) => ({ ...x, conversationId: null })); }
      setState((x) => fail(x, err.status, err.status === 429 ? err.retryAfter : err.detail));
    } finally {
      if (abort.current === ctrl) { abort.current = null; setBusy(false); }
    }
  }, [onEvent]);

  /**
   * The stream closed without `done`: mark the turn interrupted, then re-read the conversation a few times, because the
   * backend finishes and saves the turn even after the client is gone. The saved version replaces the chat once it has
   * the reply (its tool calls move to `restoredTools`).
   */
  async function recover() {
    setState(interrupt);
    for (let i = 0; i < RECOVER_TRIES; i++) {
      await new Promise((done) => setTimeout(done, RECOVER_MS));
      const cid = live.current.state.conversationId;
      if (!cid) return;
      try {
        const view = await getConversation(cid);
        const saved = fromConversation(view);
        if (view.turns[view.turns.length - 1]?.role === "assistant" && saved.turns.length >= live.current.state.turns.length) {
          setState(saved);
          break;
        }
      } catch { return; /* keep the interrupted turn */ }
    }
    live.current.s.refresh().catch(() => undefined);
  }

  const reset = useCallback(async () => {
    abort.current?.abort();
    abort.current = null;
    setBusy(false);
    const cid = live.current.state.conversationId;
    setState(EMPTY);
    writeCid(null);
    if (cid) await deleteConversation(cid).catch(() => undefined); // 404: already gone
  }, []);

  return { state, busy, enabled, restoring, send, reset };
}

/** After `step`, fetch the snapshots of the cycles it ran and describe them in one line (the web has no run viewer). */
async function summariseSnapshots(sid: string, rid: string, result: unknown): Promise<string | null> {
  const r = (result ?? {}) as { run?: { cycle?: number }; cycles?: { cycle?: number }[] };
  const ran = r.cycles?.length ?? 0;
  const start = Math.max(0, (r.run?.cycle ?? ran) - ran);
  try {
    const out = (await getRunSnapshots(sid, rid, start)) as { snapshots?: { cycle?: number }[] };
    const snaps = out.snapshots ?? [];
    if (!snaps.length) return null;
    const cycles = snaps.map((x) => x.cycle).filter((c): c is number => typeof c === "number");
    const range = cycles.length ? ` (ciclos ${Math.min(...cycles)}–${Math.max(...cycles)})` : "";
    return `${snaps.length} ${snaps.length === 1 ? "instantánea cargada" : "instantáneas cargadas"} de la corrida${range}`;
  } catch {
    return null;
  }
}

function readCid(): string | null {
  try { return localStorage.getItem(CID_KEY); } catch { return null; }
}
function writeCid(cid: string | null) {
  try { if (cid) localStorage.setItem(CID_KEY, cid); else localStorage.removeItem(CID_KEY); } catch { /* storage blocked */ }
}
