import { AGENT } from "../session/sessionApi";
import { errorMessage } from "./labels";
import { createSseParser, type SseEvent } from "./sse";

/** Client of the in-app assistant (docs/assistant.md sections 2 and 2b). */
export const ASSISTANT_BASE = "/api/v1/assistant";
export const MAX_MESSAGE = 2000;

export interface ChatBody { message: string; conversation_id?: string; session_id?: string }
export interface ConversationView {
  conversation_id: string; session_id: string | null; run_id: string | null;
  turns: { role: string; text: string }[];
  tool_calls: { name: string; arguments?: unknown; ok: boolean; result?: unknown }[];
}

/** An HTTP error before the stream started (422, 404, 429 with Retry-After, 503), or status 0 for a network failure. */
export class AssistantError extends Error {
  constructor(public status: number, public retryAfter: number | null = null, public detail: unknown = null) {
    super(errorMessage(status, retryAfter));
  }
}

/**
 * POSTs one message to `/chat/stream` and calls `onEvent` for each event as it arrives. Resolves `true` when the stream
 * ended with `done` or `error`, `false` when it closed before (a dropped connection: the backend still finishes and saves
 * the turn, so re-read the conversation). Throws `AssistantError` for an HTTP error before the stream.
 */
export async function streamChat(body: ChatBody, onEvent: (e: SseEvent) => void, signal?: AbortSignal): Promise<boolean> {
  let res: Response;
  try {
    res = await fetch(`${ASSISTANT_BASE}/chat/stream`, {
      method: "POST", signal,
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", "X-Sub50-Agent": AGENT },
      body: JSON.stringify(body),
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new AssistantError(0);
  }
  if (!res.ok || !res.body) throw await toError(res);
  let finished = false;
  const parser = createSseParser((e) => {
    if (e.event === "done" || e.event === "error") finished = true;
    onEvent(e);
  });
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      parser.push(decoder.decode(value, { stream: true }));
    }
    parser.push(decoder.decode());
    parser.flush();
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    return finished; // the connection dropped mid-stream
  }
  return finished;
}

export async function getConversation(cid: string): Promise<ConversationView> {
  const res = await call("GET", cid);
  return (await res.json()) as ConversationView;
}

export async function deleteConversation(cid: string): Promise<void> {
  await call("DELETE", cid);
}

async function call(method: string, cid: string): Promise<Response> {
  let res: Response;
  try {
    res = await fetch(`${ASSISTANT_BASE}/conversations/${encodeURIComponent(cid)}`, { method, headers: { "X-Sub50-Agent": AGENT } });
  } catch {
    throw new AssistantError(0);
  }
  if (!res.ok) throw await toError(res);
  return res;
}

async function toError(res: Response): Promise<AssistantError> {
  const data = await res.json().catch(() => null);
  const retry = Number(res.headers.get("Retry-After"));
  return new AssistantError(res.status, Number.isFinite(retry) && retry > 0 ? retry : null, data?.detail ?? data);
}
