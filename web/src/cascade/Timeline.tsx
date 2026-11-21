import { useRef } from "react";
import { BLACKOUT_HZ, markerLabel, type IslandFrequency, type Marker } from "./simulation";
import { hz, secs } from "./text";
import type { Timeline as TimelineData } from "./types";
import { Chevron, Info } from "./ui";

export const TRACK_W = 290;
export const SPEEDS = [1, 2, 4];
/** Shared vertical scale for every frame (design.md 3.2): y = 11 - 4 x (Hz - 50) in a 22 px band. */
const yOf = (f: number) => Math.max(0, Math.min(22, 11 - 4 * (f - 50)));
const faultCurve = (c: [number, number][]) => Math.min(...c.map((p) => p[1])) < 49;

interface Props {
  timeline: TimelineData | null; markers: Marker[]; t: number; clock: string; islands: IslandFrequency[]; playing: boolean; speed: number;
  setPlaying(b: boolean): void; togglePlay(): void; seek(t: number): void; setSpeed(s: number): void;
  /** A cut is chosen and its timeline is still loading: the empty hint would be wrong. */
  loading?: boolean;
}

/** Bottom card (Design v5): clock, frequency of each island, play, and the rail with numbered event markers. */
export function TimelineCard(p: Props) {
  const duration = p.timeline?.duration_s ?? 0;
  const hasCascade = !!p.timeline && p.timeline.events.length > 1;
  const x = (t: number) => (duration > 0 ? (Math.min(t, duration) / duration) * TRACK_W : 0);
  const markers = hasCascade ? p.markers : [];
  const visible = p.timeline?.events.filter((e) => e.t <= p.t + 1e-9).length ?? 0;
  const atEnd = duration > 0 && p.t >= duration - 1e-6;
  const track = useRef<HTMLDivElement>(null);

  const seekFromPointer = (clientX: number) => {
    const r = track.current!.getBoundingClientRect();
    p.seek(Math.max(0, Math.min(1, (clientX - r.left) / r.width)) * duration);
  };

  return (
    <section className="timeline" aria-label="Línea de tiempo">
      <div className="timeline-head">
        <span className="clock">{p.clock}</span>
        <div className="timeline-tools">
          <Readout islands={p.islands} />
          <label className="speed">
            <span>{p.speed}×</span><Chevron />
            <select aria-label="Velocidad" value={p.speed} onChange={(e) => p.setSpeed(Number(e.target.value))}>
              {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
            </select>
          </label>
        </div>
      </div>
      {!p.timeline ? (
        <p className="timeline-empty">{p.loading ? "Cargando la simulación" : "Sin corte activo. Haz doble clic en una línea del mapa para simular su salida de servicio segundo a segundo."}</p>
      ) : (
      <div className="timeline-row">
        <button className="play" disabled={!hasCascade} aria-label={p.playing ? "Pausa" : atEnd ? "Repetir" : "Reproducir"}
          onClick={p.togglePlay}>
          <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden>
            {p.playing ? <path d="M3 2v6M7 2v6" fill="none" stroke="#1E1F21" strokeWidth="1.8" strokeLinecap="round" />
              : atEnd ? <path d="M7.8 3.6A3.2 3.2 0 1 0 8 6M8 1.6v2.2H5.8" fill="none" stroke="#1E1F21" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                : <path d="M2.5 1.5v7l6-3.5z" fill="#1E1F21" />}
          </svg>
        </button>
        <div className="track-area" ref={track} role="slider" tabIndex={hasCascade ? 0 : -1} aria-label="Tiempo de la simulación"
          aria-valuemin={0} aria-valuemax={duration} aria-valuenow={Number(p.t.toFixed(1))} aria-valuetext={`${secs(p.t)} de ${secs(duration)} segundos`}
          onPointerDown={(e) => { if (!hasCascade) return; p.setPlaying(false); e.currentTarget.setPointerCapture(e.pointerId); seekFromPointer(e.clientX); }}
          onPointerMove={(e) => { if (e.currentTarget.hasPointerCapture(e.pointerId)) seekFromPointer(e.clientX); }}
          onKeyDown={(e) => {
            const step = e.shiftKey ? 1 : 0.1;
            if (e.key === "ArrowRight") p.seek(Math.min(duration, p.t + step));
            else if (e.key === "ArrowLeft") p.seek(Math.max(0, p.t - step));
            else if (e.key === "Home") p.seek(0);
            else if (e.key === "End") p.seek(duration);
            else return;
            e.preventDefault();
          }}>
          <svg className="curves" width={TRACK_W} height="22" viewBox={`0 0 ${TRACK_W} 22`} aria-hidden>
            <path d={`M0 11 H${TRACK_W}`} fill="none" stroke="#FFFFFF1F" strokeDasharray="3 3" />
            {p.timeline && Object.entries(p.timeline.frequency_hz).map(([id, c]) => {
              const shown = c.filter((pt) => pt[0] <= p.t + 1e-9);
              if (shown.length < 2) return null;
              return <polyline key={id} fill="none" stroke={faultCurve(c) ? "#FF5A48" : "#C9CBCF"} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
                points={shown.map((pt) => `${x(pt[0]).toFixed(1)},${yOf(pt[1]).toFixed(1)}`).join(" ")} />;
            })}
          </svg>
          <div className="track-rail" />
          <div className="track-rail played" style={{ width: x(p.t) }} />
          {!hasCascade && <div className="head" style={{ left: x(p.t) }} />}
          {markers.map((m) => <TrackMarker key={m.first} m={m} state={stateOf(m, visible)} onClick={() => p.seek(m.events[m.events.length - 1].t)} />)}
        </div>
        <div className="timeline-right">
          <span className="ref">50 Hz</span>
          <span className="pos">{`${atEnd ? Math.round(duration) : secs(p.t)} / ${Math.round(duration)} s`}</span>
        </div>
      </div>
      )}
    </section>
  );
}

export type MarkerState = "past" | "current" | "future";
export const stateOf = (m: Marker, visible: number): MarkerState => (m.last <= visible - 1 ? "past" : m.first <= visible ? "current" : "future");

function TrackMarker({ m, state, onClick }: { m: Marker; state: MarkerState; onClick(): void }) {
  // The current marker is 4 px larger (24 px with a 2 px ring), so it shifts 2 px to stay centered.
  const left = state === "current" ? m.left - 2 : m.left;
  return (
    <button className={`marker ${state}${m.first !== m.last ? " group" : ""}`} style={{ left }} onClick={(e) => { e.stopPropagation(); onClick(); }}
      onPointerDown={(e) => e.stopPropagation()} aria-label={`Evento ${markerLabel(m)}`}>
      {markerLabel(m)}
    </button>
  );
}

function Readout({ islands }: { islands: IslandFrequency[] }) {
  const live = islands.filter((i) => i.started);
  const tip = `Frecuencia de cada isla según el motor Sub50. Bajo ${hz(BLACKOUT_HZ)} Hz la isla se apaga.`;
  if (live.length === 0) return <div className="readout"><span>País <em>50,00 Hz</em></span><Info tip={tip} /></div>;
  return (
    <div className="readout">
      <span>
        {live.map((i, k) => (
          <span key={i.id}>{k > 0 && " · "}{i.name} <em className={i.collapsed || (i.hz ?? 50) < 49 ? "fault" : ""}>{i.collapsed ? "apagón" : `${hz(i.hz ?? 50)} Hz`}</em></span>
        ))}
      </span>
      <Info tip={tip} />
    </div>
  );
}
