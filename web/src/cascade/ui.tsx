import { useEffect, useRef, useState, type ReactNode } from "react";

/** Info icon next to a number: hover or focus shows where the number comes from (design.md section 2, "Numbers"). */
export function Info({ tip }: { tip: string }) {
  return (
    <span className="info" tabIndex={0} role="img" aria-label={tip} data-tip={tip}>
      <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden><circle cx="8" cy="8" r="6" fill="none" stroke="#8A8B90" strokeWidth="1.3" /><path d="M8 7.3v3.6M8 5v.1" fill="none" stroke="#8A8B90" strokeWidth="1.4" strokeLinecap="round" /></svg>
    </span>
  );
}

/**
 * One floating tooltip for every `[data-tip]` element. Why: the panel scrolls and clips, so a CSS tooltip inside it
 * would be cut at the panel edge; this one is fixed to the viewport.
 */
export function TipLayer() {
  const [tip, setTip] = useState<{ text: string; x: number; y: number; below: boolean } | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const show = (e: Event) => {
      const el = (e.target as Element | null)?.closest?.("[data-tip]");
      if (!el) return setTip(null);
      const r = el.getBoundingClientRect();
      const below = r.bottom + 120 < window.innerHeight;
      setTip({ text: el.getAttribute("data-tip") ?? "", x: r.left + r.width / 2, y: below ? r.bottom + 6 : r.top - 6, below });
    };
    const hide = () => setTip(null);
    document.addEventListener("pointerover", show);
    document.addEventListener("focusin", show);
    document.addEventListener("focusout", hide);
    document.addEventListener("scroll", hide, true);
    return () => {
      document.removeEventListener("pointerover", show);
      document.removeEventListener("focusin", show);
      document.removeEventListener("focusout", hide);
      document.removeEventListener("scroll", hide, true);
    };
  }, []);
  if (!tip) return null;
  const width = 260;
  const left = Math.max(8, Math.min(window.innerWidth - width - 8, tip.x - width / 2));
  return <div ref={ref} className="tip" role="tooltip" style={{ left, width, top: tip.y, transform: tip.below ? undefined : "translateY(-100%)" }}>{tip.text}</div>;
}

/**
 * "Copiar enlace" (F-20): an icon button that copies the page URL, which mirrors the view (url.ts), and confirms with
 * "Enlace copiado" for two seconds. The shell offers it only when the URL describes what is on screen.
 */
export function CopyLink() {
  const [state, setState] = useState<"idle" | "done" | "failed">("idle");
  useEffect(() => {
    if (state === "idle") return;
    const id = setTimeout(() => setState("idle"), 2000);
    return () => clearTimeout(id);
  }, [state]);
  const copy = () => {
    const done = () => setState("done"), failed = () => setState("failed");
    try { navigator.clipboard.writeText(location.href).then(done, failed); } catch { failed(); }
  };
  const label = state === "done" ? "Enlace copiado" : state === "failed" ? "No se pudo copiar el enlace" : "Copiar enlace";
  return (
    <span className="copy-link">
      {state !== "idle" && <span className="copy-done" role="status">{label}</span>}
      <button className="icon-btn" aria-label={label} data-tip={state === "idle" ? "Copiar enlace a esta simulación" : undefined} onClick={copy}>
        <Icon size={14}><path d="M6.5 9.5l3-3M7 4.5l1.2-1.2a2.5 2.5 0 0 1 3.5 3.5L10.5 8M9 11.5l-1.2 1.2a2.5 2.5 0 0 1-3.5-3.5L5.5 8" /></Icon>
      </button>
    </span>
  );
}

/** `color` defaults to the muted gray; pass "currentColor" to let CSS decide (the rail's disclosure chevrons). */
export const Chevron = ({ dir = "down", color = "#A1A2A6" }: { dir?: "down" | "right"; color?: string }) => (
  <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden><path d={dir === "down" ? "M2.5 4l2.5 2.5L7.5 4" : "M4 2.5l2.5 2.5L4 7.5"} fill="none" stroke={color} strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" /></svg>
);

export function Icon({ children, size = 15, view = 16 }: { children: ReactNode; size?: number; view?: number }) {
  return <svg width={size} height={size} viewBox={`0 0 ${view} ${view}`} fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" aria-hidden>{children}</svg>;
}

// Subscript "5" and power-button "0", the same paths as web/public/favicon.svg, so the proportions match the logo.
const FIVE_PATH =
  "M2 19.3 5.87 19.14Q6.06 20.03 6.68 20.47Q7.29 20.91 8.32 20.91Q9.5 20.91 10.15 20.26Q10.8 19.61 10.8 18.43Q10.8 17.32 10.13 16.64Q9.45 15.95 8.31 15.95Q7.44 15.95 6.82 16.34Q6.21 16.72 5.94 17.33H2.14L3.25 8.05H13.66V11.19H6.47L5.95 15.36L5.56 15.04Q6.14 14.21 7.13 13.73Q8.12 13.26 9.48 13.26Q11.07 13.26 12.27 13.93Q13.46 14.61 14.1 15.79Q14.73 16.96 14.73 18.43Q14.73 20.18 13.95 21.45Q13.16 22.71 11.72 23.39Q10.27 24.07 8.32 24.07Q5.38 24.07 3.79 22.8Q2.19 21.54 2 19.3Z";
const POWER_PATH = "M19.36 12.39A5.55 5.55 0 1 0 26.49 12.39M22.92 7.93V15.97";

/** Sub50 wordmark: "sub" with a subscript 5 and a power-button 0 (design.md section 6). */
export function Wordmark() {
  return (
    <div className="wordmark" aria-label="Sub50">
      <span className="sub">
        sub
        <svg className="subscript" viewBox="2 7.93 28.01 16.14" aria-hidden>
          <path d={FIVE_PATH} fill="currentColor" />
          <path d={POWER_PATH} fill="none" stroke="currentColor" strokeWidth="3.06" />
        </svg>
      </span>
    </div>
  );
}
