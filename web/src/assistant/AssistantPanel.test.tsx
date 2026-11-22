import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AssistantTurnView } from "./AssistantPanel";
import type { AssistantTurn } from "./steps";

const steps: AssistantTurn["steps"] = [
  { step: 1, items: [{ kind: "text", text: "Reviso la red." }, { kind: "tool", card: { id: "t1", name: "describe_network", arguments: {}, status: "ok", result: {} } }] },
];
const render = (turn: AssistantTurn) => renderToStaticMarkup(<AssistantTurnView turn={turn} last busy={false} onContinue={() => {}} />);

describe("assistant turn", () => {
  it("shows only a spinner while the model works, with no thoughts or tool cards", () => {
    const html = render({ role: "assistant", status: "streaming", steps });
    expect(html).toContain("Pensando…");
    expect(html).not.toContain("Reviso la red.");
    expect(html).not.toContain("tool-card");
  });

  it("shows the reply and keeps the steps in a collapsed details block once done", () => {
    const html = render({ role: "assistant", status: "done", steps, reply: "Listo." });
    expect(html).not.toContain("Pensando…");
    expect(html).toContain("Listo.");
    expect(html).toMatch(/<details class="chat-restored"><summary>Detalles del trabajo \(1 herramienta\)<\/summary>/);
  });
});
