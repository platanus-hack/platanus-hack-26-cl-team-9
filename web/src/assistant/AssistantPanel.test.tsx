// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssistantPanel } from "./AssistantPanel";
import { EMPTY } from "./steps";
import type { Assistant } from "./useAssistant";

afterEach(cleanup);
Element.prototype.scrollIntoView = vi.fn();

const assistant = (over: Partial<Assistant> = {}): Assistant => ({
  state: EMPTY, busy: false, enabled: true, restoring: false, probe: vi.fn(), send: vi.fn(async () => {}), reset: vi.fn(async () => {}), ...over,
});

describe("AssistantPanel", () => {
  it("asks once whether the assistant is available when the view opens, and repeats no title", () => {
    const a = assistant();
    render(<AssistantPanel a={a} />);
    expect(a.probe).toHaveBeenCalledOnce();
    expect(screen.queryByRole("heading", { name: "Asistente" })).toBeNull();
    expect(screen.getByText("Enter envía · Shift+Enter, nueva línea")).toBeTruthy();
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).placeholder).not.toMatch(/\bR\d{3}\b/);
  });

  it("shows one notice when it is not available, with the box and the button disabled and no shortcut hint", () => {
    const failed = { ...EMPTY, turns: [{ role: "user" as const, text: "hola" }, { role: "assistant" as const, steps: [], status: "error" as const, error: { status: 503, detail: null } }] };
    render(<AssistantPanel a={assistant({ enabled: false, state: failed as unknown as Assistant["state"] })} />);
    expect(screen.getAllByText(/no está disponible en este servidor/).length).toBe(1);
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Enviar" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByText("Enter envía · Shift+Enter, nueva línea")).toBeNull();
  });
});
