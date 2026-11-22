import { describe, expect, it } from "vitest";
import { annotate, begin, EMPTY, fail, fromConversation, interrupt, reduce, type AssistantTurn, type ChatState } from "./steps";

const run = (state: ChatState, events: [string, unknown][]) => events.reduce((s, [event, data]) => reduce(s, { event, data }), state);
const last = (s: ChatState) => s.turns[s.turns.length - 1] as AssistantTurn;

describe("reduce", () => {
  it("groups text and tool cards by step and pairs a result with its call by id", () => {
    const s = run(begin(EMPTY, "Agrega un datacenter"), [
      ["start", { conversation_id: "c1", session_id: null, run_id: null }],
      ["assistant_text", { step: 1, text: "Agrego el datacenter." }],
      ["tool_call", { step: 1, id: "t1", name: "add_datacenter", arguments: { bus: "Antofagasta", mw: 120 } }],
      ["tool_call", { step: 1, id: "t2", name: "describe_network", arguments: {} }],
      ["tool_result", { step: 1, id: "t2", name: "describe_network", ok: false, result: { error: "x" }, session_id: "s1", run_id: null }],
      ["tool_result", { step: 1, id: "t1", name: "add_datacenter", ok: true, result: { id: "D001" }, session_id: "s1", run_id: null }],
      ["tool_call", { step: 2, id: "t3", name: "cut_lines", arguments: { lines: ["R014"] } }],
    ]);
    expect(s.conversationId).toBe("c1");
    expect(s.sessionId).toBe("s1");
    expect(s.turns[0]).toEqual({ role: "user", text: "Agrega un datacenter" });
    const t = last(s);
    expect(t.status).toBe("streaming");
    expect(t.steps.map((x) => x.step)).toEqual([1, 2]);
    expect(t.steps[0].items[0]).toEqual({ kind: "text", text: "Agrego el datacenter." });
    const cards = t.steps[0].items.flatMap((i) => (i.kind === "tool" ? [i.card] : []));
    expect(cards.map((c) => [c.id, c.status])).toEqual([["t1", "ok"], ["t2", "failed"]]);
    expect(cards[0].result).toEqual({ id: "D001" });
    expect(t.steps[1].items[0]).toMatchObject({ kind: "tool", card: { id: "t3", status: "running" } });
  });

  it("done sets the reply, notice, truncation and ids, and stops cards still running", () => {
    const s = run(begin(EMPTY, "hola"), [
      ["tool_call", { step: 1, id: "t1", name: "step", arguments: { cycles: 3 } }],
      ["done", { conversation_id: "c1", session_id: "s1", run_id: "r1", reply: "Listo.", steps: 1, truncated: "steps", notice: "Supuesto." }],
    ]);
    const t = last(s);
    expect(t).toMatchObject({ status: "done", reply: "Listo.", notice: "Supuesto.", truncated: "steps" });
    expect(s.runId).toBe("r1");
    expect(t.steps[0].items[0]).toMatchObject({ card: { status: "failed" } });
  });

  it("error replaces done and keeps the steps already shown", () => {
    const s = run(begin(EMPTY, "hola"), [["assistant_text", { step: 1, text: "Voy." }], ["error", { status: 502, detail: "x" }]]);
    expect(last(s)).toMatchObject({ status: "error", error: { status: 502, detail: "x" } });
    expect(last(s).steps).toHaveLength(1);
  });

  it("keeps previous turns and ids across a second message", () => {
    const first = run(begin(EMPTY, "uno"), [["done", { conversation_id: "c1", session_id: "s1", run_id: null, reply: "a", steps: 1, truncated: null, notice: null }]]);
    const second = run(begin(first, "dos"), [["start", { conversation_id: "c1", session_id: null, run_id: null }]]);
    expect(second.turns).toHaveLength(4);
    expect(second.sessionId).toBe("s1");
  });

  it("interrupt and fail end only a streaming turn; annotate adds a line to a card", () => {
    const s = run(begin(EMPTY, "x"), [["tool_call", { step: 1, id: "t1", name: "step", arguments: {} }]]);
    expect(last(interrupt(s)).status).toBe("interrupted");
    expect(last(fail(s, 429, null))).toMatchObject({ status: "error", error: { status: 429 } });
    const done = run(s, [["done", { reply: "ok" }]]);
    expect(last(interrupt(done)).status).toBe("done");
    expect(last(annotate(s, "t1", "3 ciclos")).steps[0].items[0]).toMatchObject({ card: { extra: "3 ciclos" } });
  });
});

describe("fromConversation", () => {
  it("merges the assistant texts of one message and keeps the tool trace apart", () => {
    const s = fromConversation({
      conversation_id: "c1", session_id: "s1", run_id: null,
      turns: [{ role: "user", text: "Agrega" }, { role: "assistant", text: "Agrego." }, { role: "assistant", text: "Listo." }, { role: "user", text: "Corta" }, { role: "assistant", text: "Cortada." }],
      tool_calls: [{ name: "add_datacenter", arguments: { mw: 120 }, ok: true, result: { id: "D001" } }, { name: "cut_lines", ok: false, result: "x" }],
    });
    expect(s.sessionId).toBe("s1");
    expect(s.turns.map((t) => t.role)).toEqual(["user", "assistant", "user", "assistant"]);
    expect(s.turns[1]).toMatchObject({ status: "done", reply: "Listo.", steps: [{ step: 1, items: [{ kind: "text", text: "Agrego." }] }] });
    expect(s.restoredTools.map((c) => [c.name, c.status])).toEqual([["add_datacenter", "ok"], ["cut_lines", "failed"]]);
  });
});
