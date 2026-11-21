import { BLACKOUT_HIGH_HZ, BLACKOUT_LOW_HZ, describeBalance, describeCurves, describeOutcome, NOMINAL_HZ, wholeGridCurve } from "./frequency";
import type { Event, Timeline } from "./types";

const W = 360, H = 196, L = 34, R = 10, T = 18, B = 26;

/** What the grid frequency does in each island after the cut. `now` is the stage time shown on the map. */
export function FrequencyChart({ curves, events, now }: { curves: Timeline["frequency_hz"]; events: Event[]; now: number }) {
  const found = describeCurves(curves, events);
  const stable = found.length === 0; // no island lost its balance: show the whole grid holding 50 Hz instead of an empty chart
  const list = stable ? [wholeGridCurve(events)] : found;
  const tMax = Math.max(5, Math.ceil(Math.max(...list.map((c) => c.end)) / 5) * 5);
  const hzMax = list.some((c) => c.maxHz > 51) ? 52 : 51, hzMin = 47;
  const x = (t: number) => L + (t / tMax) * (W - L - R);
  const y = (f: number) => T + ((hzMax - Math.min(Math.max(f, hzMin), hzMax)) / (hzMax - hzMin)) * (H - T - B);
  const hzTicks = Array.from({ length: hzMax - hzMin + 1 }, (_, i) => hzMin + i);
  const tTicks = Array.from({ length: tMax / 5 + 1 }, (_, i) => i * 5);
  const cursor = x(Math.min(now, tMax));
  return (
    <figure className="freq">
      <h3>{stable ? "Frecuencia de la red" : "Frecuencia de cada isla"}</h3>
      <p className="muted">
        {stable
          ? "La red sigue conectada y lo que se genera iguala lo que se consume, por eso la frecuencia se mantiene en 50 Hz. Si un corte la partiera en islas, aquí verías la frecuencia de cada una."
          : "El corte partió la red en islas: grupos de subestaciones que quedaron separados del resto. Cada isla debe producir lo mismo que consume. Si le falta generación su frecuencia cae, si le sobra sube. Bajo 47,5 Hz la isla se apaga."}
      </p>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Frecuencia en Hz de cada isla, en función del tiempo en segundos">
        <rect x={L} y={y(BLACKOUT_LOW_HZ)} width={W - L - R} height={H - B - y(BLACKOUT_LOW_HZ)} fill="#ef4444" opacity="0.14" />
        {hzTicks.map((f) => (
          <g key={f}>
            <line x1={L} x2={W - R} y1={y(f)} y2={y(f)} stroke="#2c2d31" />
            <text x={L - 6} y={y(f) + 3} textAnchor="end" className="tick">{f}</text>
          </g>
        ))}
        {tTicks.map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={H - B} y2={H - B + 4} stroke="#8d8e94" />
            <text x={x(t)} y={H - B + 14} textAnchor="middle" className="tick">{t}</text>
          </g>
        ))}
        <text x={4} y={9} className="tick">Hz</text>
        <text x={W - R} y={H - 2} textAnchor="end" className="tick">segundos desde el corte</text>
        <line x1={L} x2={W - R} y1={y(NOMINAL_HZ)} y2={y(NOMINAL_HZ)} stroke="#8d8e94" strokeDasharray="4 3" />
        <text x={W - R - 2} y={y(NOMINAL_HZ) - 3} textAnchor="end" className="tick">50 Hz: normal</text>
        <line x1={L} x2={W - R} y1={y(BLACKOUT_LOW_HZ)} y2={y(BLACKOUT_LOW_HZ)} stroke="#ef4444" strokeDasharray="4 3" />
        <text x={W - R - 2} y={y(BLACKOUT_LOW_HZ) - 3} textAnchor="end" className="tick red">47,5 Hz: se apaga</text>
        {hzMax === 52 && (
          <g>
            <line x1={L} x2={W - R} y1={y(BLACKOUT_HIGH_HZ)} y2={y(BLACKOUT_HIGH_HZ)} stroke="#ef4444" strokeDasharray="4 3" />
            <text x={L + 4} y={y(BLACKOUT_HIGH_HZ) + 11} className="tick red">52 Hz: se apaga</text>
          </g>
        )}
        <line x1={cursor} x2={cursor} y1={T} y2={H - B} stroke="#e6e6e8" strokeOpacity="0.5" />
        {list.map((c) => {
          const last = c.points[c.points.length - 1];
          return (
            <g key={c.key}>
              <polyline fill="none" stroke={c.color} strokeWidth="2" strokeLinejoin="round" points={c.points.map((p) => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ")} />
              {c.collapsed ? (
                <g stroke="#ef4444" strokeWidth="2" strokeLinecap="round">
                  <line x1={x(c.end) - 4} x2={x(c.end) + 4} y1={y(last[1]) - 4} y2={y(last[1]) + 4} />
                  <line x1={x(c.end) - 4} x2={x(c.end) + 4} y1={y(last[1]) + 4} y2={y(last[1]) - 4} />
                </g>
              ) : (
                <circle cx={x(c.end)} cy={y(c.finalHz)} r="3" fill={c.color} />
              )}
            </g>
          );
        })}
      </svg>
      <ul className="freq-legend">
        {list.map((c) => (
          <li key={c.key}>
            <span className="chip" style={{ background: c.color }}>{c.letter || "●"}</span>
            <span>
              <b>{c.wholeGrid ? "Toda la red" : `Isla ${c.letter}`}</b>{describeBalance(c) && ` · ${describeBalance(c)}`}
              <br />
              {describeOutcome(c)}{c.collapsed && <span className="x"> ✕</span>}
            </span>
          </li>
        ))}
      </ul>
      <figcaption className="muted">{stable ? "" : "✕ marca el instante en que la isla se apaga. "}La línea vertical es el momento que ves en el mapa.</figcaption>
    </figure>
  );
}
