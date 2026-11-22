import { describe, expect, it } from "vitest";
import { createSseParser, type SseEvent } from "./sse";

function parse(chunks: string[], flush = false): SseEvent[] {
  const out: SseEvent[] = [];
  const p = createSseParser((e) => out.push(e));
  chunks.forEach((c) => p.push(c));
  if (flush) p.flush();
  return out;
}

describe("createSseParser", () => {
  it("parses complete blocks into event and JSON data", () => {
    const out = parse(['event: start\ndata: {"conversation_id": "c1", "session_id": null}\n\nevent: assistant_text\ndata: {"step": 1, "text": "Agrego"}\n\n']);
    expect(out).toEqual([
      { event: "start", data: { conversation_id: "c1", session_id: null } },
      { event: "assistant_text", data: { step: 1, text: "Agrego" } },
    ]);
  });

  it("joins blocks cut anywhere across chunks", () => {
    const text = 'event: tool_call\ndata: {"step": 1, "id": "t1", "name": "add_datacenter"}\n\n';
    const chunks = [text.slice(0, 3), text.slice(3, 20), text.slice(20, text.length - 1), text.slice(text.length - 1)];
    expect(parse(chunks)).toEqual([{ event: "tool_call", data: { step: 1, id: "t1", name: "add_datacenter" } }]);
  });

  it("ignores ping comments and blocks without an event line", () => {
    expect(parse([": ping\n\n", "data: {}\n\n", 'event: done\ndata: {"steps": 2}\n\n'])).toEqual([{ event: "done", data: { steps: 2 } }]);
  });

  it("accepts CRLF line ends, also split between chunks", () => {
    expect(parse(['event: done\r\ndata: {"steps": 1}\r', "\n\r\n"])).toEqual([{ event: "done", data: { steps: 1 } }]);
    expect(parse(["event: done\r", '\ndata: {"steps": 1}\r\n\r\n'])).toEqual([{ event: "done", data: { steps: 1 } }]);
  });

  it("joins multi-line data with a newline", () => {
    expect(parse(['event: done\ndata: {"reply":\ndata: "hola"}\n\n'])).toEqual([{ event: "done", data: { reply: "hola" } }]);
  });

  it("keeps a trailing partial block until it completes or is flushed", () => {
    expect(parse(['event: done\ndata: {"steps": 3}'])).toEqual([]);
    expect(parse(['event: done\ndata: {"steps": 3}'], true)).toEqual([{ event: "done", data: { steps: 3 } }]);
  });

  it("passes data that is not JSON as text", () => {
    expect(parse(["event: error\ndata: boom\n\n"])).toEqual([{ event: "error", data: "boom" }]);
  });
});
