import { useCallback, useEffect, useRef, useState } from "react";
import type { Frame, Timeline } from "../cascade/types";
import { incidentError } from "../incidents/incidents";
import { ApiError, createRun, createSession, getRunReport, getSimCatalog, stepRun, submitRunAction } from "../session/sessionApi";
import { frames as toFrames, invalidFields, runBody, type CyberCatalog, type CyberFrame, type CyberReport, type Defense } from "./cyber";

const CYCLE_MS = 1400; // one cycle on screen at 1×; the timeline card's speed (2×, 4×) divides it
const BASE_POINT = "nov2026-1300"; // the standard grid: the original nodes at the default hour

export interface Queued { action: string; target: string; label: string }
export type Sub = "territorio" | "jugadas" | "componente" | "salud" | "reglas";
export interface CyberRun {
  sid: string; runId: string; seed: number | null; defense: Defense; frames: CyberFrame[]; report: CyberReport | null; finished: boolean;
  horizon: number; // cycles the run may last; the progress bar is played cycles over this
}
export interface Cyber {
  catalog: CyberCatalog | null; llmAvailable: boolean; params: Record<string, number>; defense: Defense; crews: number; seed: number | null;
  busy: boolean; error: string | null; run: CyberRun | null; at: number; playing: boolean; mapCycle: number | null; queued: Queued[];
  load(): void; setParam(k: string, v: number): void; setDefense(d: Defense): void; setCrews(n: number): void; setSeed(s: number | null): void;
  launch(): Promise<void>; seek(i: number): void; play(): void; pause(): void; close(): void;
  showOnMap(cycle: number | null): void; cascadeAt(cycle: number): Timeline | null;
  /** The grid of the cycle on screen, for the map: dark substations, open and overloaded lines. */
  gridNow: Frame | null;
  sub: Sub; setSub(s: Sub): void;
  /** Play or pause: live turns while the run is on (algorithm or LLM), replay once it finished. */
  togglePlay(): void;
  queue(action: string, target: string, label: string): Promise<void>; endTurn(): Promise<void>;
}

/**
 * State of the Ciberataque monitor, owned by CascadeApp so it survives view changes. `launch` always opens a fresh session
 * at the base point (original nodes, no edits) and creates the run with the form's values. The run is played turn by
 * turn: with an algorithm or the LLM one cycle every CYCLE_MS / speed (the timeline card's speed); with the user
 * defending, `queue` sends an action through `POST .../actions` (validated and paid for by the backend) and `endTurn`
 * plays the cycle. A finished run can be replayed with the slider.
 */
export function useCyber(speed = 1): Cyber {
  const [catalog, setCatalog] = useState<CyberCatalog | null>(null);
  const [llmAvailable, setLlm] = useState(false);
  const [params, setParams] = useState<Record<string, number>>({});
  const [defense, setDefense] = useState<Defense>("C");
  const [crews, setCrews] = useState(9);
  const [seed, setSeed] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<CyberRun | null>(null);
  const [at, setAt] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [mapCycle, setMapCycle] = useState<number | null>(null);
  const [queued, setQueued] = useState<Queued[]>([]);
  const [sub, setSub] = useState<Sub>("territorio");
  const live = useRef({ catalog, params, defense, crews, seed, busy, run, playing });
  live.current = { catalog, params, defense, crews, seed, busy, run, playing };
  const stepping = useRef(false); // one live step call at a time

  const load = useCallback(() => {
    if (live.current.catalog) return;
    getSimCatalog().then((raw) => {
      const cat = raw.cyber_attack as CyberCatalog | undefined;
      if (!cat) throw new Error("El servidor no ofrece el escenario Ciberataque.");
      setCatalog(cat); setParams({ ...cat.defaults }); setCrews(cat.crews_default ?? 9);
      setLlm(Boolean((raw.llm as { available?: boolean } | undefined)?.available));
    }).catch((e) => setError(errorOf(e)));
  }, []);

  // Live turns (algorithm or LLM, run still on) and the replay of a finished run: one cycle per CYCLE_MS / speed.
  useEffect(() => {
    if (!playing || !run) return;
    if (!run.finished && run.defense !== "user") {
      if (stepping.current) return;
      const t = setTimeout(() => {
        stepping.current = true;
        advanceRef.current(run, 1).catch((e) => { setError(errorOf(e)); setPlaying(false); }).finally(() => { stepping.current = false; });
      }, CYCLE_MS / speed);
      return () => clearTimeout(t);
    }
    if (at >= run.frames.length - 1) { setPlaying(false); return; }
    const t = setTimeout(() => setAt((i) => i + 1), CYCLE_MS / speed);
    return () => clearTimeout(t);
  }, [playing, at, run, speed]);

  /** Steps `cycles`, appends the frames and, once the backend says the run finished, reads the report. */
  const advance = useCallback(async (base: CyberRun, cycles: number): Promise<CyberRun> => {
    const stepped = await stepRun(base.sid, base.runId, cycles);
    const snaps = (stepped.snapshots ?? []) as Parameters<typeof toFrames>[0];
    const finished = (stepped.run as { status?: string } | undefined)?.status === "finished" || !snaps.length;
    let next: CyberRun = { ...base, frames: [...base.frames, ...toFrames(snaps)], finished };
    if (finished) next = { ...next, report: ((await getRunReport(base.sid, base.runId)).cyber_attack ?? null) as CyberReport | null };
    setRun(next);
    setAt(Math.max(0, next.frames.length - 1));
    return next;
  }, []);

  const advanceRef = useRef(advance);
  advanceRef.current = advance;

  const launch = useCallback(async () => {
    const { catalog: cat, params: p, defense: d, crews: c, seed: sd, busy: running } = live.current;
    if (!cat || running) return;
    const bad = invalidFields(cat, p);
    if (bad.length) { setError(`Revisa estos valores: ${bad.join(", ")}.`); return; }
    setBusy(true); setError(null); setRun(null); setAt(0); setPlaying(false); setMapCycle(null); setQueued([]);
    try {
      const doc = await createSession({ point: BASE_POINT, label: "Ciberataque" });
      const created = await createRun(doc.session_id, runBody(cat, p, d, c, sd));
      let cur: CyberRun = {
        sid: doc.session_id, runId: String(created.run_id), seed: typeof created.seed === "number" ? created.seed : null,
        defense: d, frames: [], report: null, finished: false, horizon: Number(created.horizon) || 72,
      };
      setRun(cur);
      cur = await advance(cur, 1); // cycle 0: the intrusion appears
      if (d !== "user") setPlaying(true); // then the turns play by themselves, one by one
    } catch (e) {
      setError(errorOf(e));
    } finally {
      setBusy(false);
    }
  }, [advance]);

  const queue = useCallback(async (action: string, target: string, label: string) => {
    const r = live.current.run;
    if (!r || r.finished || live.current.busy) return;
    setError(null);
    try {
      await submitRunAction(r.sid, r.runId, { action, target, role: "operations", agent: "usuario" });
      setQueued((q) => [...q, { action, target, label }]);
    } catch (e) {
      setError(errorOf(e));
    }
  }, []);

  const endTurn = useCallback(async () => {
    const r = live.current.run;
    if (!r || r.finished || live.current.busy) return;
    setBusy(true); setError(null);
    try {
      await advance(r, 1);
      setQueued([]);
    } catch (e) {
      setError(errorOf(e));
    } finally {
      setBusy(false);
    }
  }, [advance]);

  const cascadeAt = useCallback((cycle: number) => run?.frames.find((f) => f.cycle === cycle)?.transient ?? null, [run]);
  const gridNow = run?.frames[at]?.grid ?? null;
  const play = () => { if (run?.finished && at >= run.frames.length - 1) setAt(0); setPlaying(true); };
  return {
    sub, setSub, togglePlay: () => (playing ? setPlaying(false) : play()),
    gridNow, catalog, llmAvailable, params, defense, crews, seed, busy, error, run, at, playing, mapCycle, queued,
    load, setParam: (k, v) => setParams((x) => ({ ...x, [k]: v })), setDefense, setCrews, setSeed, launch, cascadeAt, queue, endTurn,
    seek: (i) => { setPlaying(false); setAt(i); },
    play,
    pause: () => setPlaying(false),
    close: () => { setRun(null); setPlaying(false); setMapCycle(null); setError(null); setQueued([]); setSub("territorio"); },
    showOnMap: setMapCycle,
  };
}

function errorOf(e: unknown): string {
  if (e instanceof ApiError) return incidentError(e.status, e.message, e.retryAfter);
  return incidentError(e instanceof TypeError ? null : 0, (e as Error).message);
}
