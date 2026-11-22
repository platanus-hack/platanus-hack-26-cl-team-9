import type { ReactNode } from "react";

/**
 * The little Markdown the model writes (paragraphs, "-" and "1." lists, **bold**, `code`, "###" headings) as React
 * elements. Before, the reply was plain text and showed the asterisks. Everything stays text nodes: the model's words
 * and the element names it repeats are data and never become HTML.
 */
export type Block =
  | { kind: "p"; lines: string[] }
  | { kind: "ul" | "ol"; items: string[] }
  | { kind: "h"; text: string };

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const HEADING = /^\s*#{1,6}\s+(.*)$/;

export function blocks(text: string): Block[] {
  const out: Block[] = [];
  for (const raw of text.replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    const last = out[out.length - 1];
    const bullet = BULLET.exec(line);
    const numbered = bullet ? null : NUMBERED.exec(line);
    const heading = HEADING.exec(line);
    if (!line.trim()) {
      out.push({ kind: "p", lines: [] }); // a blank line closes the block
    } else if (heading) {
      out.push({ kind: "h", text: heading[1] });
    } else if (bullet || numbered) {
      const kind = bullet ? "ul" : "ol";
      const item = (bullet ?? numbered)![1];
      if (last?.kind === kind) last.items.push(item);
      else out.push({ kind, items: [item] });
    } else if (last?.kind === "p") {
      last.lines.push(line);
    } else if ((last?.kind === "ul" || last?.kind === "ol") && /^\s{2,}/.test(raw)) {
      last.items[last.items.length - 1] += ` ${line.trim()}`; // an indented line continues the item
    } else {
      out.push({ kind: "p", lines: [line] });
    }
  }
  return out.filter((b) => b.kind !== "p" || b.lines.length > 0);
}

/** **bold** and `code` inside one line; an unpaired marker stays as written. */
export function inline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  const re = /\*\*(.+?)\*\*|`([^`]+)`/g;
  let at = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > at) out.push(text.slice(at, m.index));
    out.push(m[1] !== undefined ? <b key={m.index}>{m[1]}</b> : <code key={m.index}>{m[2]}</code>);
    at = m.index + m[0].length;
  }
  if (at < text.length) out.push(text.slice(at));
  return out;
}

export function Markdown({ text, className }: Readonly<{ text: string; className?: string }>) {
  return (
    <div className={className}>
      {blocks(text).map((b, i) => {
        if (b.kind === "h") return <p key={i} className="md-h">{inline(b.text)}</p>;
        if (b.kind === "p") return <p key={i}>{b.lines.flatMap((l, k) => (k ? [<br key={`br${k}`} />, ...inline(l)] : inline(l)))}</p>;
        const items = b.items.map((it, k) => <li key={k}>{inline(it)}</li>);
        return b.kind === "ul" ? <ul key={i}>{items}</ul> : <ol key={i}>{items}</ol>;
      })}
    </div>
  );
}
