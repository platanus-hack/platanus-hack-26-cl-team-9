import { useCallback, useEffect, useRef, useState } from "react";
import type { Timeline } from "../cascade/types";
import { incidentError } from "../incidents/incidents";
import { ApiError, createRun, createSession, getRunReport, getSimCatalog, stepRun } from "../session/sessionApi";
import { frames as toFrames, invalidFields, runBody, type CyberCatalog, type CyberFrame, type CyberReport, type Defense } from "./cyber";

const CHUNK = 6; // cycles per step call: the view fills in while the run goes on
const PLAY_MS = 700;
const BASE_POINT = "nov2026-1300"; // the standard grid: the original nodes at the default hour

export interface CyberRun { sid: string; runId: string; seed: number | null; frames: CyberFrame[]; report: CyberReport | null; llm: boolean }
export interface Cyber {
  catalog: CyberCatalog | null; llmAvailable: boolean; params: Record<string, number>; defense: Defense; crews: number; seed: number | null;
  busy: boolean; error: string | null; run: CyberRun | null; at: number; playing: boolean; mapCycle: number | null;
  load(): void; setParam(k: string, v: number): void; setDefense(d: Defense): void; setCrews(n: number): void; setSeed(s: number | null): void;
  launch(): Promise<void>; seek(i: number): void; play(): void; pause(): void; close(): void;
  showOnMap(cycle: number | null): void; cascadeAt(cycle: number): Timeline | null;
}

/**
 * State of the Ciberataque view, owned by CascadeApp so it survives view changes. `launch` always opens a fresh session at
 * the base point (the original nodes, no edits), creates the run with the form's values and steps it until the backend
 * says it finished, in chunks, so the frames appear as they are simulated. The defence is a rules policy (A, B, C) or the
 * server's LLM commander; nothing is decided here.
 */
export function useCyber(): Cyber {
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
  const live = useRef({ catalog, params, defense, crews, seed, busy });
  live.current = { catalog, params, defense, crews, seed, busy };

  const load = useCallback(() => {
    if (live.current.catalog) return;
    getSimCatalog().then((raw) => {
      const cat = raw.cyber_attack as CyberCatalog | undefined;
      if (!cat) throw new Error("El servidor no ofrece el escenario Ciberataque.");
      setCatalog(cat); setParams({ ...cat.defaults }); setCrews(cat.crews_default ?? 9);
      setLlm(Boolean((raw.llm as { available?: boolean } | undefined)?.available));
    }).catch((e) => setError(errorOf(e)));
  }, []);

  useEffect(() => {
    if (!playing || !run) return;
    if (at >= run.frames.length - 1) { setPlaying(false); return; }
    const t = setTimeout(() => setAt((i) => i + 1), PLAY_MS);
    return () => clearTimeout(t);
  }, [playing, at, run]);

  const launch = useCallback(async () => {
    const { catalog: cat, params: p, defense: d, crews: c, seed: sd, busy: running } = live.current;
    if (!cat || running) return;
    const bad = invalidFields(cat, p);
    if (bad.length) { setError(`Revisa estos valores: ${bad.join(", ")}.`); return; }
    setBusy(true); setError(null); setRun(null); setAt(0); setPlaying(false); setMapCycle(null);
    try {
      const doc = await createSession({ point: BASE_POINT, label: "Ciberataque" });
      const sid = doc.session_id;
      const created = await createRun(sid, runBody(cat, p, d, c, sd));
      const rid = String(created.run_id);
      const base: CyberRun = { sid, runId: rid, seed: typeof created.seed === "number" ? created.seed : null, frames: [], report: null, llm: d === "llm" };
      let all: CyberFrame[] = [];
      for (;;) {
        const stepped = await stepRun(sid, rid, CHUNK);
        const snaps = (stepped.snapshots ?? []) as Parameters<typeof toFrames>[0];
        all = [...all, ...toFrames(snaps)];
        setRun({ ...base, frames: all });
        setAt(Math.max(0, all.length - 1));
        const info = stepped.run as { status?: string } | undefined;
        if (!snaps.length || info?.status === "finished") break;
      }
      const report = await getRunReport(sid, rid);
      setRun({ ...base, frames: all, report: (report.cyber_attack ?? null) as CyberReport | null });
    } catch (e) {
      setError(errorOf(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const cascadeAt = useCallback((cycle: number) => run?.frames.find((f) => f.cycle === cycle)?.transient ?? null, [run]);
  return {
    catalog, llmAvailable, params, defense, crews, seed, busy, error, run, at, playing, mapCycle,
    load, setParam: (k, v) => setParams((x) => ({ ...x, [k]: v })), setDefense, setCrews, setSeed, launch, cascadeAt,
    seek: (i) => { setPlaying(false); setAt(i); },
    play: () => { if (run && at >= run.frames.length - 1) setAt(0); setPlaying(true); },
    pause: () => setPlaying(false),
    close: () => { setRun(null); setPlaying(false); setMapCycle(null); setError(null); },
    showOnMap: setMapCycle,
  };
}

function errorOf(e: unknown): string {
  if (e instanceof ApiError) return incidentError(e.status, e.message, e.retryAfter);
  return incidentError(e instanceof TypeError ? null : 0, (e as Error).message);
}
