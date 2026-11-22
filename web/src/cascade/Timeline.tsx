import { useRef } from "react";
import { BLACKOUT_HZ, floorTenths, islandDash, markerLabel, type IslandFrequency, type Marker, type TimeWarp } from "./simulation";
import { hz, secs } from "./text";
import type { Timeline as TimelineData } from "./types";
import { Info } from "./ui";

export const TRACK_W = 290;
export const SPEEDS = [1, 2, 4];
/** Shared vertical scale for every frame (design.md 3.2): y = 11 - 4 x (Hz - 50) in a 22 px band. */
const yOf = (f: number) => Math.max(0, Math.min(22, 11 - 4 * (f - 50)));
const faultCurve = (c: [number, number][]) => Math.min(...c.map((p) => p[1])) < 49;

interface Props {
  timeline: TimelineData | null; markers: Marker[]; t: number; clock: string; islands: IslandFrequency[]; playing: boolean; speed: number;
  /** Non-linear track scale (simulation.ts `timeWarp`): x positions, dragging and arrow keys go through it. */
  warp: TimeWarp;
  setPlaying(b: boolean): void; togglePlay(): void; seek(t: number): void; setSpeed(s: number): void;
  /** A cut is chosen and its timeline is still loading. */
  loading?: boolean;
  /** The simulation of the changes failed (the panel says why and offers Reintentar). */
  failed?: boolean;
  /** Every substation is dark at `t`: the readout says "apagón", never 50 Hz (D3). */
  blackout?: boolean;
}

/**
 * Bottom card (Design v5): clock, frequency of each island, play, and the rail with numbered event markers. The rail
 * uses the warped time (each failure gets room, the quiet tail is short); the clock and the position read simulated s,
 * both rounded down to tenths. The shell renders it only while there is a timeline to play (D9): how to start one is
 * said by the cold start card in Simulación, not here.
 */
export function TimelineCard(p: Props) {
  const duration = p.timeline?.duration_s ?? 0;
  const hasCascade = !!p.timeline && p.timeline.events.length > 0;
  const view = p.warp.viewDuration;
  const x = (t: number) => (view > 0 ? (Math.min(p.warp.toView(t), view) / view) * TRACK_W : 0);
  const seekView = (v: number) => p.seek(Math.max(0, Math.min(duration, p.warp.toSim(Math.max(0, Math.min(view, v))))));
  const markers = hasCascade ? p.markers : [];
  const visible = p.timeline?.events.filter((e) => e.t <= p.t + 1e-9).length ?? 0;
  const atEnd = duration > 0 && p.t >= duration - 1e-6;
  const track = useRef<HTMLDivElement>(null);

  const seekFromPointer = (clientX: number) => {
    const r = track.current!.getBoundingClientRect();
    seekView(Math.max(0, Math.min(1, (clientX - r.left) / r.width)) * view);
  };

  return (
    <section className="timeline" aria-label="Línea de tiempo">
      <div className="timeline-head">
        <span className="clock">{p.clock}</span>
        <div className="timeline-tools">
          {p.timeline && <Readout islands={p.islands} blackout={!!p.blackout} />}
          {/* The segmented control, not a native select (D16, E-15). */}
          <div className="seg speed-seg" role="group" aria-label="Velocidad">
            {SPEEDS.map((s) => <button key={s} className={p.speed === s ? "on" : ""} aria-pressed={p.speed === s} onClick={() => p.setSpeed(s)}>{s}×</button>)}
          </div>
        </div>
      </div>
      {!p.timeline ? (
        <p className="timeline-empty">{p.failed ? "No se pudo simular este cambio." : "Cargando la simulación"}</p>
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
            const step = e.shiftKey ? 1 : 0.1; // track seconds, so a step moves the same distance anywhere on the rail
            if (e.key === "ArrowRight") seekView(p.warp.toView(p.t) + step);
            else if (e.key === "ArrowLeft") seekView(p.warp.toView(p.t) - step);
            else if (e.key === "Home") p.seek(0);
            else if (e.key === "End") p.seek(duration);
            else return;
            e.preventDefault();
          }}>
          <svg className="curves" width={TRACK_W} height="22" viewBox={`0 0 ${TRACK_W} 22`} aria-hidden>
            <path d={`M0 11 H${TRACK_W}`} fill="none" stroke="#FFFFFF1F" strokeDasharray="3 3" />
            {p.timeline && Object.entries(p.timeline.frequency_hz).map(([id, c], k) => {
              const shown = c.filter((pt) => pt[0] <= p.t + 1e-9);
              if (shown.length < 2) return null;
              // Each island keeps its stroke pattern, the same as its swatch in the readout (A2-08); red only under 49 Hz.
              return <polyline key={id} fill="none" stroke={faultCurve(c) ? "#FF5A48" : "#C9CBCF"} strokeWidth="1.5" strokeLinecap="butt" strokeLinejoin="round"
                strokeDasharray={islandDash(k) || undefined} points={shown.map((pt) => `${x(pt[0]).toFixed(1)},${yOf(pt[1]).toFixed(1)}`).join(" ")} />;
            })}
          </svg>
          <div className="track-rail" />
          <div className="track-rail played" style={{ width: x(p.t) }} />
          <div className="head" style={{ left: x(p.t) }} />
          {markers.map((m) => <TrackMarker key={m.first} m={m} state={stateOf(m, visible)} onClick={() => p.seek(m.events[m.events.length - 1].t)} />)}
        </div>
        <div className="timeline-right">
          <span className="ref">50 Hz</span>
          <span className="pos">{`${atEnd ? Math.round(duration) : secs(floorTenths(p.t))} / ${Math.round(duration)} s`}</span>
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

/** Swatch of an island's stroke pattern, so each curve of the rail can be told apart (A2-08). */
const IslandSwatch = ({ k, fault }: { k: number; fault: boolean }) => (
  <svg className="island-swatch" width="14" height="6" viewBox="0 0 14 6" aria-hidden>
    <path d="M0 3H14" fill="none" stroke={fault ? "#FF5A48" : "#C9CBCF"} strokeWidth="1.5" strokeDasharray={islandDash(k) || undefined} />
  </svg>
);

/**
 * Frequency of each island with its stroke swatch. With three or more islands the readout wraps onto two short lines
 * and names each island only by its swatch and the tip. With every substation dark it reads "apagón" (D3).
 */
function Readout({ islands, blackout }: { islands: IslandFrequency[]; blackout: boolean }) {
  const tip = `Frecuencia de cada isla según el motor Sub50; cada isla tiene su trazo en la curva. Bajo ${hz(BLACKOUT_HZ)} Hz la isla se apaga.`;
  if (blackout) return <div className="readout"><span>País <em className="fault">apagón</em></span><Info tip={tip} /></div>;
  const live = islands.map((i, k) => ({ i, k })).filter(({ i }) => i.started);
  if (live.length === 0) return <div className="readout"><span>País <em>50,00 Hz</em></span><Info tip={tip} /></div>;
  const many = live.length > 2;
  return (
    <div className={many ? "readout many" : "readout"}>
      <span className="readout-list">
        {live.map(({ i, k }) => {
          const fault = i.collapsed || (i.hz ?? 50) < 49;
          return (
            <span key={i.id} className="readout-item" title={i.name}>
              <IslandSwatch k={k} fault={fault} />{!many && <>{i.name} </>}<em className={fault ? "fault" : ""}>{i.collapsed ? "apagón" : `${hz(i.hz ?? 50)} Hz`}</em>
            </span>
          );
        })}
      </span>
      <Info tip={many ? `${live.map(({ i }) => `${i.name}: ${i.collapsed ? "apagón" : `${hz(i.hz ?? 50)} Hz`}`).join(" · ")}. ${tip}` : tip} />
    </div>
  );
}
