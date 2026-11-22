import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssistantError, getConversation, PROBE_CID, probeAssistant, streamChat } from "./assistantApi";
import type { SseEvent } from "./sse";

const stream = (chunks: string[]) => new Response(new ReadableStream({
  start(c) { const enc = new TextEncoder(); chunks.forEach((x) => c.enqueue(enc.encode(x))); c.close(); },
}), { status: 200, headers: { "Content-Type": "text/event-stream" } });

describe("assistantApi", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => { fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock); });
  afterEach(() => vi.unstubAllGlobals());

  it("posts the message and reads the events until done", async () => {
    fetchMock.mockResolvedValue(stream(['event: start\ndata: {"conversation_id": "c1"}\n\n: pi', 'ng\n\nevent: done\ndata: {"reply": "ok"}\n\n']));
    const events: SseEvent[] = [];
    const finished = await streamChat({ message: "hola", session_id: "s1" }, (e) => events.push(e));
    expect(finished).toBe(true);
    expect(events.map((e) => e.event)).toEqual(["start", "done"]);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/assistant/chat/stream");
    expect(init.headers).toMatchObject({ "X-Sub50-Agent": "web", "Content-Type": "application/json" });
    expect(JSON.parse(init.body)).toEqual({ message: "hola", session_id: "s1" });
  });

  it("reports a stream that closed before done", async () => {
    fetchMock.mockResolvedValue(stream(['event: assistant_text\ndata: {"step": 1, "text": "x"}\n\n']));
    expect(await streamChat({ message: "hola" }, () => undefined)).toBe(false);
  });

  it("throws AssistantError with Retry-After before the stream", async () => {
    fetchMock.mockResolvedValue(new Response(JSON.stringify({ detail: "slow down" }), { status: 429, headers: { "Retry-After": "12" } }));
    const err = await streamChat({ message: "hola" }, () => undefined).catch((e) => e);
    expect(err).toBeInstanceOf(AssistantError);
    expect(err).toMatchObject({ status: 429, retryAfter: 12, message: "Demasiados mensajes; espera 12 s." });
  });

  it("maps a network failure to status 0 and a missing conversation to 404", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    await expect(streamChat({ message: "x" }, () => undefined)).rejects.toMatchObject({ status: 0 });
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "no" }), { status: 404 }));
    await expect(getConversation("abc")).rejects.toMatchObject({ status: 404 });
  });

  it("probes availability by reading a conversation that does not exist: 503 off, 404 on, anything else unknown", async () => {
    expect(PROBE_CID).toMatch(/^[A-Za-z0-9_-]{22}$/);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "off" }), { status: 503 }));
    expect(await probeAssistant()).toBe(false);
    expect(fetchMock.mock.calls[0][0]).toBe(`/api/v1/assistant/conversations/${PROBE_CID}`);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: "no" }), { status: 404 }));
    expect(await probeAssistant()).toBe(true);
    fetchMock.mockRejectedValueOnce(new TypeError("offline"));
    expect(await probeAssistant()).toBeNull();
  });
});
