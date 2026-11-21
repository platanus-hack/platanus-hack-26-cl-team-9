import type { Timeline } from "./types";

/** One curve per island, 47-51 Hz, with the 47.5 Hz blackout limit. Shared by the cut viewer and the operation mode. */
export function FrequencyChart({ curves }: { curves: Timeline["frequency_hz"] }) {
  const entries = Object.entries(curves);
  if (!entries.length) return <p className="muted">Sin desbalance de potencia: la frecuencia se mantiene en 50 Hz.</p>;
  const tMax = Math.max(...entries.flatMap(([, c]) => c.map((p) => p[0])), 1);
  const x = (t: number) => (t / tMax) * 300, y = (f: number) => 80 - ((f - 47) / 4) * 80;
  return (
    <figure>
      <svg viewBox="0 0 300 80" className="chart">
        <line x1="0" x2="300" y1={y(50)} y2={y(50)} stroke="#475569" strokeDasharray="3 3" />
        <line x1="0" x2="300" y1={y(47.5)} y2={y(47.5)} stroke="#ef4444" strokeDasharray="3 3" />
        {entries.map(([id, c], i) => <polyline key={id} fill="none" stroke={["#7dd3fc", "#fbbf24", "#a78bfa", "#34d399"][i % 4]} strokeWidth="1.2" points={c.map((p) => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ")} />)}
      </svg>
      <figcaption className="muted">Frecuencia por isla (47–51 Hz). Línea roja: 47,5 Hz, límite de apagón.</figcaption>
    </figure>
  );
}
