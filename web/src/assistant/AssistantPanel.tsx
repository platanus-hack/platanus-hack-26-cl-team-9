import { useEffect, useRef, useState } from "react";
import { MAX_MESSAGE } from "./assistantApi";
import { argsText, errorMessage, resultText, toolName, truncatedText } from "./labels";
import { Markdown } from "./markdown";
import type { AssistantTurn, Step, ToolCard } from "./steps";
import type { Assistant } from "./useAssistant";
import "./assistant.css";

const CONTINUE = "continúa";

/**
 * The Asistente view of mapa 3 (docs/assistant.md section 2c): the history with each step of the model as it happens
 * (text, tool cards with their state, final reply), and the message box. It shows only what the tools returned; the
 * scenario notice goes with each reply because it carries the assumption note (AGENTS.md section 4).
 */
export function AssistantPanel({ a }: { a: Assistant }) {
  const [text, setText] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const { turns, restoredTools } = a.state;
  const lastTurn = turns[turns.length - 1];
  useEffect(() => { endRef.current?.scrollIntoView({ block: "end" }); }, [turns]);

  const submit = (msg: string) => {
    if (!msg.trim() || msg.length > MAX_MESSAGE || a.busy || !a.enabled) return;
    void a.send(msg);
    setText("");
  };
  const tooLong = text.length > MAX_MESSAGE;

  return (
    <div className="assistant">
      <div className="card">
        <div className="card-head">
          <h3>Asistente</h3>
          <button className="text-btn" onClick={() => void a.reset()} disabled={!turns.length && !a.state.conversationId}>Nueva conversación</button>
        </div>
        <p className="meta">Pide en lenguaje natural lo que quieres simular: agregar un datacenter, cortar líneas, avanzar una corrida. El mapa muestra lo que el asistente cambia en la sesión.</p>
      </div>

      {!a.enabled && <p className="note">{errorMessage(503)}</p>}
      {a.restoring && <p className="meta">Recuperando la conversación…</p>}

      {restoredTools.length > 0 && (
        <details className="chat-restored">
          <summary>Herramientas que ya usó esta conversación ({restoredTools.length})</summary>
          <div className="chat-steps">{restoredTools.map((c) => <ToolCardView key={c.id} card={c} />)}</div>
        </details>
      )}

      {turns.map((t, i) => (t.role === "user"
        ? <p key={i} className="chat-user">{t.text}</p>
        : <AssistantTurnView key={i} turn={t} last={t === lastTurn} onContinue={() => submit(CONTINUE)} busy={a.busy} />))}

      <form className="chat-form" onSubmit={(e) => { e.preventDefault(); submit(text); }}>
        <textarea aria-label="Mensaje para el asistente" rows={2} placeholder={a.enabled ? "Agrega un datacenter de 120 MW en Antofagasta y corta R014" : "El asistente no está disponible"}
          value={text} disabled={!a.enabled} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); submit(text); } }} />
        <div className="chat-form-foot">
          <span className={tooLong ? "meta fault" : "meta"}>{text.length.toLocaleString("es-CL")} / {MAX_MESSAGE.toLocaleString("es-CL")}</span>
          <span className="meta">Enter envía · Shift+Enter, nueva línea</span>
          <button type="submit" className="btn" disabled={!a.enabled || a.busy || !text.trim() || tooLong}>{a.busy ? "Trabajando…" : "Enviar"}</button>
        </div>
      </form>
      <div ref={endRef} />
    </div>
  );
}

export function AssistantTurnView({ turn, last, busy, onContinue }: { turn: AssistantTurn; last: boolean; busy: boolean; onContinue(): void }) {
  const truncated = truncatedText(turn.truncated);
  const streaming = turn.status === "streaming";
  const tools = turn.steps.reduce((n, s) => n + s.items.filter((i) => i.kind === "tool").length, 0);
  return (
    <div className="chat-turn" aria-live={last ? "polite" : undefined}>
      {streaming && <p className="meta chat-wait"><span className="spinner" aria-hidden />Pensando…</p>}
      {turn.reply && <Markdown className="chat-reply" text={turn.reply} />}
      {turn.notice && <div className="notice"><span>{turn.notice}</span></div>}
      {truncated && (
        <div className="notice"><span>{truncated}</span>{last && <button className="text-btn" disabled={busy} onClick={onContinue}>Continuar</button>}</div>
      )}
      {turn.status === "error" && turn.error && <p className="note">{errorMessage(turn.error.status, typeof turn.error.detail === "number" ? turn.error.detail : null)}</p>}
      {turn.status === "interrupted" && <p className="note">Se cortó la conexión antes de terminar. El servidor termina el mensaje y lo guarda: se intenta recuperar la respuesta.</p>}
      {!streaming && turn.steps.length > 0 && (
        <details className="chat-restored">
          <summary>Detalles del trabajo ({tools} {tools === 1 ? "herramienta" : "herramientas"})</summary>
          {turn.steps.map((s) => <StepView key={s.step} step={s} />)}
        </details>
      )}
    </div>
  );
}

function StepView({ step }: { step: Step }) {
  return (
    <div className="chat-steps">
      {step.items.map((item, i) => (item.kind === "text"
        ? <Markdown key={i} className="chat-thought" text={item.text} />
        : <ToolCardView key={item.card.id || i} card={item.card} />))}
    </div>
  );
}

function ToolCardView({ card }: { card: ToolCard }) {
  const args = argsText(card.name, card.arguments);
  const summary = card.status === "running" ? "" : resultText(card.name, card.status === "ok", card.result);
  return (
    <div className={`tool-card ${card.status}`}>
      <div className="tool-head">
        <span className="tool-mark" aria-hidden>{card.status === "running" ? <span className="spinner" /> : card.status === "ok" ? "✓" : "✗"}</span>
        <b>{toolName(card.name)}</b>
        <span className="meta tool-state">{card.status === "running" ? "ejecutando…" : card.status === "ok" ? "listo" : "falló"}</span>
      </div>
      {args && <p className="meta tool-args">{args}</p>}
      {summary && <p className="tool-summary">{summary}</p>}
      {card.extra && <p className="meta">{card.extra}</p>}
      {card.status !== "running" && card.result !== undefined && (
        <details className="tool-detail">
          <summary>Ver resultado</summary>
          <pre>{JSON.stringify(card.result, null, 2)}</pre>
        </details>
      )}
    </div>
  );
}
