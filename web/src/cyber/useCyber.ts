import { useCallback, useEffect, useRef, useState } from "react";
import type { Timeline } from "../cascade/types";
import { incidentError, visible } from "../incidents/incidents";
import { ApiError, createRun, createSession, getRunReport, getSimCatalog, stepRun } from "../session/sessionApi";
import { defaultTexts, formFields, frames as toFrames, parseField, readForm, runBody, type CyberCatalog, type CyberFrame, type CyberReport, type Defense } from "./cyber";

const CHUNK = 6; // cycles per step call: the view fills in while the run goes on
const PLAY_MS = 700;
const DEFAULT_HORIZON = 24;
const BASE_POINT = "nov2026-1300"; // the standard grid: the original nodes at the default hour

export interface CyberRun {
  sid: string; runId: string; seed: number | null; frames: CyberFrame[]; report: CyberReport | null; defense: Defense;
  horizon: number; params: Record<string, number>; crews: number; done: boolean;
}
export interface Cyber {
  catalog: CyberCatalog | null; llmAvailable: boolean; texts: Record<string, string>; errors: Record<string, string>; defense: Defense;
  busy: boolean; error: string | null; run: CyberRun | null; at: number; playing: boolean; mapCycle: number | null;
  load(): void; setText(k: string, v: string): void; check(k: string): void; resetParams(): void; setDefense(d: Defense): void;
  launch(): Promise<void>; seek(i: number): void; play(): void; pause(): void; close(): void;
  showOnMap(cycle: number | null): void; cascadeAt(cycle: number): Timeline | null;
}

/**
 * State of the Ciberataque view, owned by CascadeApp so it survives view changes. The form keeps what the user types
 * (`texts`) and checks a field against the catalog bounds when it loses focus (`check`), so a value is never rewritten
 * while it is typed; `launch` checks every field and stops while one is invalid. It opens a fresh session at the base
 * point (the original nodes, no edits), creates the run and steps it in chunks until the backend says it finished, so
 * the frames appear as they are simulated. When the run ends, the first cycle with a cascade is shown on the map. One
 * run at a time. The defence is a rules policy (A, B, C) or the server's LLM commander; nothing is decided here.
 */
export function useCyber(): Cyber {
  const [catalog, setCatalog] = useState<CyberCatalog | null>(null);
  const [llmAvailable, setLlm] = useState(false);
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [defense, setDefense] = useState<Defense>("C");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [run, setRun] = useState<CyberRun | null>(null);
  const [at, setAt] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [mapCycle, setMapCycle] = useState<number | null>(null);
  const live = useRef({ catalog, texts, defense });
  live.current = { catalog, texts, defense };
  const launching = useRef(false); // set synchronously: a second activation in the same tick does not start a second run
  const loading = useRef(false);

  const load = useCallback(() => {
    if (live.current.catalog || loading.current) return;
    loading.current = true;
    setError(null);
    getSimCatalog().then((raw) => {
      const cat = raw.cyber_attack as CyberCatalog | undefined;
      if (!cat) throw new Error("El servidor no ofrece el escenario Ciberataque.");
      setCatalog(cat); setTexts(defaultTexts(cat)); setErrors({});
      setLlm(Boolean((raw.llm as { available?: boolean } | undefined)?.available));
    }).catch((e) => setError(errorOf(e))).finally(() => { loading.current = false; });
  }, []);

  useEffect(() => {
    if (!playing || !run) return;
    if (at >= run.frames.length - 1) { setPlaying(false); return; }
    const t = setTimeout(() => setAt((i) => i + 1), PLAY_MS);
    return () => clearTimeout(t);
  }, [playing, at, run]);

  const check = useCallback((key: string) => {
    const cat = live.current.catalog;
    const spec = cat && formFields(cat).find((f) => f.key === key);
    if (!cat || !spec) return;
    const { error: msg } = parseField(spec, live.current.texts[key] ?? "", cat);
    setErrors((e) => {
      const next = { ...e };
      if (msg) next[key] = msg; else delete next[key];
      return next;
    });
  }, []);

  const launch = useCallback(async () => {
    const { catalog: cat, texts: tx, defense: d } = live.current;
    if (!cat || launching.current) return;
    const form = readForm(cat, tx);
    setErrors(form.errors);
    if (Object.keys(form.errors).length) return;
    launching.current = true;
    setBusy(true); setError(null); setRun(null); setAt(0); setPlaying(false); setMapCycle(null);
    try {
      const doc = await createSession({ point: BASE_POINT, label: "Ciberataque" });
      const sid = doc.session_id;
      const created = await createRun(sid, runBody(cat, form.params, d, form.crews, form.seed));
      const rid = String(created.run_id);
      const base: CyberRun = {
        sid, runId: rid, seed: typeof created.seed === "number" ? created.seed : null, frames: [], report: null, defense: d,
        horizon: Number(created.horizon) || DEFAULT_HORIZON, params: { ...cat.defaults, ...form.params }, crews: form.crews, done: false,
      };
      setRun(base);
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
      setRun({ ...base, frames: all, report: (report.cyber_attack ?? null) as CyberReport | null, done: true });
      // The map shows the first cycle whose cascade has something to draw, and the slider goes to it.
      const first = all.findIndex((f) => f.transient && visible(f.transient));
      if (first >= 0) { setAt(first); setMapCycle(all[first].cycle); }
    } catch (e) {
      setError(errorOf(e));
    } finally {
      launching.current = false;
      setBusy(false);
    }
  }, []);

  const cascadeAt = useCallback((cycle: number) => run?.frames.find((f) => f.cycle === cycle)?.transient ?? null, [run]);
  return {
    catalog, llmAvailable, texts, errors, defense, busy, error, run, at, playing, mapCycle,
    load, check, launch, cascadeAt,
    setText: (k, v) => { setTexts((x) => ({ ...x, [k]: v })); setErrors((e) => { if (!(k in e)) return e; const n = { ...e }; delete n[k]; return n; }); },
    resetParams: () => { if (catalog) { setTexts(defaultTexts(catalog)); setErrors({}); } },
    setDefense: (d) => { if (!launching.current) setDefense(d); },
    seek: (i) => { setPlaying(false); setAt(i); },
    play: () => { if (run && at >= run.frames.length - 1) setAt(0); setPlaying(true); },
    pause: () => setPlaying(false),
    close: () => { setRun(null); setPlaying(false); setMapCycle(null); setError(null); },
    showOnMap: setMapCycle,
  };
}

function errorOf(e: unknown): string {
  if (e instanceof ApiError && e.status >= 500 && e.status !== 503 && e.detail == null) return incidentError(null, `error ${e.status}`);
  if (e instanceof ApiError) return incidentError(e.status, e.message, e.retryAfter);
  return incidentError(e instanceof TypeError ? null : 0, (e as Error).message);
}
