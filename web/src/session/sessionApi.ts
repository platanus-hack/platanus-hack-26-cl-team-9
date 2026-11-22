import type { Balance, SessionNetwork, SessionWarning, Timeline } from "../cascade/types";

/** Client of the sessions API (docs/sessions-api.md). Only used with ?sesion=; the no-session path reads /cache/. */
export const API = "/api/v1";
export const BASE = `${API}/sessions`;
export const AGENT = "web";
const SID = /^[A-Za-z0-9_-]{22}$/;
export type Kind = "buses" | "lines" | "loads" | "generators";
export interface LastOp { op: string; ids: string[]; by: string; revision: number; dataset_revision?: number }
export interface SessionDoc {
  session_id: string; label: string | null; point: string; revision: number; dataset_revision: number; open_lines: string[];
  runs: Record<string, { created_at: string; dataset_revision: number; cycle: number; status: string }>;
  last_op: LastOp; share_path: string; expires_at: string; created_at: string; updated_at: string;
}
export interface EditResult { id?: string; revision: number; dataset_revision: number; warnings: SessionWarning[]; balance: Balance[] }
export interface CutState { revision: number; dataset_revision: number; open_lines: string[]; timeline: Timeline; notice: string }
export interface RevisionEvent { type?: "revision"; revision: number; dataset_revision?: number; op?: string; ids?: string[]; by?: string }
type Json = Record<string, unknown>;

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown, public retryAfter: number | null = null) { super(errorText(status, detail)); }
}

/** The session id in `?sesion=`, the only place a session comes from (no URL, no session, no `/api` call); anything
 * that is not a session id is ignored. */
export function sessionIdFrom(search: string): string | null {
  const id = new URLSearchParams(search).get("sesion");
  return id && SID.test(id) ? id : null;
}
/** Retries of a busy 409 (docs/sessions-api.md section 7). The server did not run that request, so any method is safe. */
const BUSY_RETRIES = 2;
const call = <T>(method: string, path: string, opts: { body?: unknown; ifMatch?: number } = {}) => callAt<T>(BASE, method, path, opts);
/** `call` under another prefix of the API (the incident catalog lives outside /sessions). */
async function callAt<T>(base: string, method: string, path: string, opts: { body?: unknown; ifMatch?: number } = {}): Promise<T> {
  const headers: Record<string, string> = { "X-Sub50-Agent": AGENT };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (opts.ifMatch !== undefined) headers["If-Match"] = `"${opts.ifMatch}"`;
  const body = opts.body === undefined ? undefined : JSON.stringify(opts.body);
  let r = await fetch(`${base}${path}`, { method, headers, body });
  for (let i = 0; i < BUSY_RETRIES && r.status === 409 && r.headers.has("Retry-After"); i++) {
    const wait = Math.min(Number(r.headers.get("Retry-After")) || 1, 10);
    await new Promise((done) => setTimeout(done, wait * 1000));
    r = await fetch(`${base}${path}`, { method, headers, body });
  }
  if (r.status === 204) return undefined as T;
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new ApiError(r.status, data?.detail ?? data, r.headers.has("Retry-After") ? Number(r.headers.get("Retry-After")) || null : null);
  return data as T;
}
const sid = (id: string) => `/${encodeURIComponent(id)}`;
const run = (id: string, rid: string) => `${sid(id)}/runs/${encodeURIComponent(rid)}`;
export const createSession = (body: { point?: string; label?: string } = {}) => call<SessionDoc>("POST", "", { body });
export const getSession = (id: string) => call<SessionDoc>("GET", sid(id));
export const deleteSession = (id: string) => call<void>("DELETE", sid(id));
export const resetSession = (id: string, ifMatch?: number) => call<EditResult>("POST", `${sid(id)}/reset`, { ifMatch });
export const getNetwork = (id: string) => call<SessionNetwork>("GET", `${sid(id)}/network`);
export const addElement = (id: string, kind: Kind, fields: Json, ifMatch?: number) => call<EditResult>("POST", `${sid(id)}/${kind}`, { body: fields, ifMatch });
export const updateElement = (id: string, kind: Kind, element: string, fields: Json, ifMatch?: number) =>
  call<EditResult>("PATCH", `${sid(id)}/${kind}/${encodeURIComponent(element)}`, { body: fields, ifMatch });
export const deleteElement = (id: string, kind: Kind, element: string, ifMatch?: number) =>
  call<EditResult>("DELETE", `${sid(id)}/${kind}/${encodeURIComponent(element)}`, { ifMatch });
export const cutLines = (id: string, lines: string[], ifMatch?: number) => call<CutState>("POST", `${sid(id)}/cut`, { body: { lines }, ifMatch });
export const repairLines = (id: string, body: { lines?: string[]; all?: boolean }, ifMatch?: number) => call<CutState>("POST", `${sid(id)}/repair`, { body, ifMatch });
export const getState = (id: string) => call<CutState>("GET", `${sid(id)}/state`);

// Session runs of the strategic theatre (bodies as in docs/sessions-api.md section 4).
export const createRun = (id: string, body: Json) => call<Json>("POST", `${sid(id)}/runs`, { body });
export const getRun = (id: string, rid: string) => call<Json>("GET", run(id, rid));
export const injectRunEvent = (id: string, rid: string, body: { type: string; target: string; params?: Json; cause?: string }) => call<Json>("POST", `${run(id, rid)}/events`, { body });
export const stepRun = (id: string, rid: string, cycles = 1) => call<Json>("POST", `${run(id, rid)}/step`, { body: { cycles } });
export const submitRunAction = (id: string, rid: string, body: { action: string; target: string; role: string; params?: Json; agent?: string }) =>
  call<Json>("POST", `${run(id, rid)}/actions`, { body });
export const replayRun = (id: string, rid: string, body: Json = {}) => call<Json>("POST", `${run(id, rid)}/replay`, { body });
export const getRunSnapshots = (id: string, rid: string, start = 0) => call<Json>("GET", `${run(id, rid)}/snapshots?start=${start}`);
export const getRunTrace = (id: string, rid: string) => call<Json>("GET", `${run(id, rid)}/trace`);
export const getRunReport = (id: string, rid: string) => call<Json>("GET", `${run(id, rid)}/report`);
export const getRunAfterAction = (id: string, rid: string) => call<Json>("GET", `${run(id, rid)}/after_action`);

// Documented-incident scenarios (docs/attack-sim.md section 3.1): only catalog ids, no free effects.
export interface IncidentRunBody { scenario: string; policy: "A" | "B" | "C"; seed?: number }
// Catalog of the strategic theatre; its `cyber_attack` block drives the Ciberataque form (docs/attack-sim.md 3.2).
export const getSimCatalog = () => callAt<Json>(API, "GET", "/sim/catalog");
export const getIncidentCatalog = () => callAt<Json>(API, "GET", "/attacks/catalog");
export const startIncidentRun = (id: string, body: IncidentRunBody) => call<Json>("POST", `${sid(id)}/attacks/runs`, { body });
export type LiveMode = "sse" | "poll";
export interface Subscription { readonly mode: LiveMode; close(): void }

/**
 * Calls onRevision on every session change. Uses the SSE stream when EventSource exists and falls back to polling
 * GET /{sid} with If-None-Match every pollMs when it does not or when the stream cannot reconnect (error, 404, 429).
 * onGone fires when polling finds the session deleted or expired.
 */
export function subscribe(id: string, onRevision: (e: RevisionEvent) => void, opts: { pollMs?: number; onMode?(m: LiveMode): void; onGone?(): void } = {}): Subscription {
  const pollMs = opts.pollMs ?? 2000;
  let closed = false, mode: LiveMode = "poll", etag: string | null = null, timer: ReturnType<typeof setTimeout> | undefined, es: EventSource | undefined;
  const poll = async () => {
    if (closed) return;
    try {
      const r = await fetch(`${BASE}${sid(id)}`, { headers: { "X-Sub50-Agent": AGENT, ...(etag ? { "If-None-Match": etag } : {}) } });
      if (r.status === 404) { closed = true; opts.onGone?.(); return; }
      if (r.ok) {
        etag = r.headers.get("ETag");
        const doc = (await r.json()) as SessionDoc;
        if (!closed) onRevision({ type: "revision", ...doc.last_op, revision: doc.revision });
      }
    } catch (e) { console.warn("session poll failed, retrying on the next tick", e); /* network error: try again on the next tick */ }
    if (!closed) timer = setTimeout(poll, pollMs);
  };
  const startPolling = () => { mode = "poll"; opts.onMode?.("poll"); poll(); };
  if (typeof EventSource === "undefined") startPolling();
  else {
    es = new EventSource(`${BASE}${sid(id)}/events`);
    mode = "sse";
    opts.onMode?.("sse");
    es.addEventListener("revision", (e) => onRevision(JSON.parse((e as MessageEvent).data)));
    // EventSource reconnects by itself after the server closes the stream (every 55 s); CLOSED means it gave up.
    es.onerror = () => { if (!closed && es?.readyState === EventSource.CLOSED) { es.close(); startPolling(); } };
  }
  return { get mode() { return mode; }, close() { closed = true; es?.close(); clearTimeout(timer); } };
}

const FIELD_LABELS: Record<string, string> = {
  name: "Nombre", kv: "kV", lat: "Latitud", lon: "Longitud", mw: "MW", bus: "Barra", a: "Barra A", b: "Barra B", capacity_mw: "Capacidad MW",
  x_pu: "Reactancia", load_mw: "Demanda MW", gen_mw: "Generación MW", sync_mw: "Sincrónica MW", inertia_mws: "Inercia MWs", kind: "Tipo", tech: "Tecnología",
};
function errorText(status: number, detail: unknown): string {
  if (typeof detail === "string") return detail;
  // A validation error lists the fields it refused; name them as the Datos forms do.
  if (Array.isArray(detail)) {
    const fields = [...new Set(detail.map((d) => FIELD_LABELS[String((d as { loc?: unknown[] }).loc?.at(-1) ?? "")] ?? "un valor"))];
    return `El servidor no aceptó ${fields.length === 1 ? "este campo" : "estos campos"}: ${fields.join(", ")}.`;
  }
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  return `Error ${status} del servidor de sesiones.`;
}
