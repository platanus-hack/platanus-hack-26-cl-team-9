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

export const Chevron = ({ dir = "down" }: { dir?: "down" | "right" }) => (
  <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden><path d={dir === "down" ? "M2.5 4l2.5 2.5L7.5 4" : "M4 2.5l2.5 2.5L4 7.5"} fill="none" stroke="#A1A2A6" strokeWidth="1.3" strokeLinecap="round" /></svg>
);

export function Icon({ children, size = 15, view = 16 }: { children: ReactNode; size?: number; view?: number }) {
  return <svg width={size} height={size} viewBox={`0 0 ${view} ${view}`} fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round" aria-hidden>{children}</svg>;
}

/** Sub50 wordmark: "sub" with a subscript 5 and a power-button 0 (design.md section 6). */
export function Wordmark() {
  return (
    <div className="wordmark" aria-label="Sub50">
      <span className="sub">sub</span>
      <span className="subscript">
        <span>5</span>
        <svg width="8" height="11" viewBox="0 0 8 11" aria-hidden><path d="M2.1 3.2 A3.1 3.9 0 1 0 5.9 3.2" fill="none" stroke="#FFFFFF" strokeWidth="1.5" strokeLinecap="round" /><path d="M4 1 V5" fill="none" stroke="#FFFFFF" strokeWidth="1.5" strokeLinecap="round" /></svg>
      </span>
    </div>
  );
}
