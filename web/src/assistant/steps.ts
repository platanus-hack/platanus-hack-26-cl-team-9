import type { SseEvent } from "./sse";

/** One tool call in the chat: "running" from `tool_call` until its `tool_result` (same `id`) says ok or failed. */
export interface ToolCard {
  id: string; name: string; arguments: unknown; status: "running" | "ok" | "failed"; result?: unknown;
  /** Extra line the client adds after the result, e.g. the snapshots fetched after `step`. */
  extra?: string;
}
export type StepItem = { kind: "text"; text: string } | { kind: "tool"; card: ToolCard };
export interface Step { step: number; items: StepItem[] }
export interface UserTurn { role: "user"; text: string }
export interface AssistantTurn {
  role: "assistant";
  status: "streaming" | "done" | "error" | "interrupted";
  steps: Step[];
  reply?: string; notice?: string | null; truncated?: string | null;
  error?: { status: number; detail: unknown };
}
export type Turn = UserTurn | AssistantTurn;
export interface ChatState {
  conversationId: string | null; sessionId: string | null; runId: string | null;
  turns: Turn[];
  /** Tool calls restored from `GET /conversations/{cid}`, which does not say which turn ran them. */
  restoredTools: ToolCard[];
}

export const EMPTY: ChatState = { conversationId: null, sessionId: null, runId: null, turns: [], restoredTools: [] };

type Json = Record<string, unknown>;
const str = (v: unknown) => (typeof v === "string" ? v : null);

/** The user sent `text`: add their turn and an empty assistant turn that the stream fills. */
export function begin(state: ChatState, text: string): ChatState {
  return { ...state, turns: [...state.turns, { role: "user", text }, { role: "assistant", status: "streaming", steps: [] }] };
}

/** The stream closed without `done` or `error` (network drop): the running assistant turn is marked interrupted. */
export function interrupt(state: ChatState): ChatState {
  return withLast(state, (t) => (t.status === "streaming" ? { ...t, status: "interrupted", steps: t.steps.map(stopRunning) } : t));
}

/** A failure before the stream started (HTTP error or network): the running turn ends with that error. */
export function fail(state: ChatState, status: number, detail: unknown = null): ChatState {
  return withLast(state, (t) => (t.status === "streaming" ? { ...t, status: "error", error: { status, detail } } : t));
}

/** Attach an extra line to the card `id` (anywhere in the history). */
export function annotate(state: ChatState, id: string, extra: string): ChatState {
  return {
    ...state,
    turns: state.turns.map((t) => (t.role === "assistant"
      ? { ...t, steps: t.steps.map((s) => ({ ...s, items: s.items.map((i) => (i.kind === "tool" && i.card.id === id ? { ...i, card: { ...i.card, extra } } : i)) })) }
      : t)),
  };
}

/** Apply one stream event (docs/assistant.md section 2b) to the chat. Unknown events are ignored. */
export function reduce(state: ChatState, { event, data }: SseEvent): ChatState {
  const d = (data && typeof data === "object" ? data : {}) as Json;
  const ids = (s: ChatState): ChatState => ({
    ...s,
    conversationId: str(d.conversation_id) ?? s.conversationId,
    sessionId: str(d.session_id) ?? s.sessionId,
    runId: str(d.run_id) ?? s.runId,
  });
  switch (event) {
    case "start":
      return ids(state);
    case "assistant_text":
      return addItem(state, Number(d.step) || 0, { kind: "text", text: String(d.text ?? "") });
    case "tool_call":
      return addItem(state, Number(d.step) || 0, { kind: "tool", card: { id: String(d.id ?? ""), name: String(d.name ?? ""), arguments: d.arguments ?? {}, status: "running" } });
    case "tool_result": {
      const id = String(d.id ?? "");
      const status = d.ok ? "ok" : "failed";
      const next = withLast(ids(state), (t) => {
        let found = false;
        const steps = t.steps.map((s) => ({
          ...s,
          items: s.items.map((i) => (i.kind === "tool" && i.card.id === id ? ((found = true), { ...i, card: { ...i.card, status, result: d.result } as ToolCard }) : i)),
        }));
        // A result without its call (should not happen) still shows as a card in its step.
        return found ? { ...t, steps } : appendItem({ ...t }, Number(d.step) || 0, { kind: "tool", card: { id, name: String(d.name ?? ""), arguments: {}, status, result: d.result } });
      });
      return next;
    }
    case "done":
      return withLast(ids(state), (t) => ({
        ...t, status: "done", reply: String(d.reply ?? ""), notice: str(d.notice), truncated: str(d.truncated), steps: t.steps.map(stopRunning),
      }));
    case "error":
      return withLast(state, (t) => ({ ...t, status: "error", error: { status: Number(d.status) || 500, detail: d.detail ?? (typeof data === "string" ? data : null) }, steps: t.steps.map(stopRunning) }));
    default:
      return state;
  }
}

/** Rebuild the chat from `GET /conversations/{cid}`: consecutive assistant texts of one user message form one turn
 * (the last is the reply, earlier ones are the text written before acting); tool calls go to `restoredTools`. */
export function fromConversation(view: { conversation_id: string; session_id?: string | null; run_id?: string | null; turns?: { role: string; text: string }[]; tool_calls?: { name: string; arguments?: unknown; ok: boolean; result?: unknown }[] }): ChatState {
  const turns: Turn[] = [];
  for (const t of view.turns ?? []) {
    if (t.role === "user") { turns.push({ role: "user", text: t.text }); continue; }
    const last = turns[turns.length - 1];
    if (last?.role === "assistant") {
      if (last.reply) last.steps.push({ step: last.steps.length + 1, items: [{ kind: "text", text: last.reply }] });
      last.reply = t.text;
    } else turns.push({ role: "assistant", status: "done", steps: [], reply: t.text });
  }
  const restoredTools = (view.tool_calls ?? []).map((c, i): ToolCard => ({ id: `h${i}`, name: c.name, arguments: c.arguments ?? {}, status: c.ok ? "ok" : "failed", result: c.result }));
  return { conversationId: view.conversation_id, sessionId: view.session_id ?? null, runId: view.run_id ?? null, turns, restoredTools };
}

function withLast(state: ChatState, fn: (t: AssistantTurn) => AssistantTurn): ChatState {
  const last = state.turns[state.turns.length - 1];
  if (last?.role !== "assistant") return state;
  return { ...state, turns: [...state.turns.slice(0, -1), fn(last)] };
}

function addItem(state: ChatState, step: number, item: StepItem): ChatState {
  return withLast(state, (t) => appendItem(t, step, item));
}

function appendItem(t: AssistantTurn, step: number, item: StepItem): AssistantTurn {
  const i = t.steps.findIndex((s) => s.step === step);
  if (i < 0) return { ...t, steps: [...t.steps, { step, items: [item] }] };
  return { ...t, steps: t.steps.map((s, j) => (j === i ? { ...s, items: [...s.items, item] } : s)) };
}

function stopRunning(s: Step): Step {
  return { ...s, items: s.items.map((i) => (i.kind === "tool" && i.card.status === "running" ? { ...i, card: { ...i.card, status: "failed" } } : i)) };
}
