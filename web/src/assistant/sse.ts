/** One Server-Sent Event of the assistant stream: its `event:` name and its parsed `data:` JSON. */
export interface SseEvent { event: string; data: unknown }

/**
 * Incremental parser of a `text/event-stream` body (docs/assistant.md section 2b). `push` takes chunks as they arrive,
 * cut anywhere, and calls `onEvent` once per complete block. Blocks without an `event:` line (the `: ping` comments) are
 * skipped, `\r\n` is accepted, multi-line `data:` is joined with `\n`, and data that is not JSON is passed as a string.
 * `flush` parses a last block the server closed without a blank line.
 */
export function createSseParser(onEvent: (e: SseEvent) => void) {
  let buf = "";
  let cr = false; // the last chunk ended in "\r": a "\n" opening the next one belongs to it
  const emit = (block: string) => {
    let event = "";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (!line || line.startsWith(":")) continue;
      const i = line.indexOf(":");
      const field = i < 0 ? line : line.slice(0, i);
      const value = i < 0 ? "" : line.slice(i + 1).replace(/^ /, "");
      if (field === "event") event = value;
      else if (field === "data") data.push(value);
    }
    if (!event) return;
    const text = data.join("\n");
    let parsed: unknown = text;
    try { parsed = text ? JSON.parse(text) : {}; } catch { /* keep the raw text */ }
    onEvent({ event, data: parsed });
  };
  return {
    push(chunk: string) {
      if (cr && chunk.startsWith("\n")) chunk = chunk.slice(1);
      cr = chunk.endsWith("\r");
      buf += chunk.replace(/\r\n?/g, "\n");
      let i: number;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, i);
        buf = buf.slice(i + 2);
        emit(block);
      }
    },
    flush() {
      const rest = buf;
      buf = "";
      if (rest.trim()) emit(rest);
    },
  };
}
