import { useCallback, useEffect, useRef, useState } from "react";
import type { Timeline } from "../cascade/types";
import { ApiError, createSession, getIncidentCatalog, getRunAfterAction, getRunReport, startIncidentRun, stepRun } from "../session/sessionApi";
import type { Session } from "../session/useSession";
import { cascadeCycles, cycleMinutes, incidentError, pointText, sessionPlan, type AarCycle, type CascadeCycle, type IncidentAar, type IncidentCard, type IncidentCatalog, type IncidentInfo, type Indicators, type Policy, type RunSnapshot } from "./incidents";

export interface IncidentResult {
  sid: string; runId: string; seed: number | null; incident: IncidentInfo; level: string;
  card: IncidentCard; indicators: Indicators; aar: IncidentAar | null; timeline: AarCycle[]; cascades: CascadeCycle[]; minutesPerCycle: number;
}
export interface Incident {
  catalog: IncidentCatalog | null; selected: string | null; policy: Policy; durationH: number; busy: boolean; error: string | null;
  result: IncidentResult | null; playing: number | null;
  load(): void; select(id: string): void; setPolicy(p: Policy): void; setDurationH(h: number): void;
  launch(): Promise<void>; play(cycle: number): void; stop(): void; close(): void; cascadeAt(cycle: number): Timeline | null;
}

/**
 * State of the Incidentes view (docs/mapa3.md section 4.2), owned by CascadeApp so the result survives view changes.
 * An incident runs at its own hour: without a session, or in one at another hour, `launch` creates a session at the
 * incident's point and joins it (after a confirmation when it leaves another session). Then it starts the run, steps
 * it to its horizon and reads the report and the after-action. `playing` is the cycle whose cascade the map plays.
 */
export function useIncident(s: Session): Incident {
  const [catalog, setCatalog] = useState<IncidentCatalog | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [policy, setPolicy] = useState<Policy>("C");
  const [durationH, setDurationH] = useState(4);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IncidentResult | null>(null);
  const [playing, setPlaying] = useState<number | null>(null);
  const live = useRef({ s, catalog, selected, policy, durationH, busy });
  live.current = { s, catalog, selected, policy, durationH, busy };
  const loading = useRef(false);

  const load = useCallback(() => {
    if (live.current.catalog || loading.current) return;
    loading.current = true;
    getIncidentCatalog().then((raw) => {
      const cat = raw as unknown as IncidentCatalog;
      setCatalog(cat); setError(null);
      setDurationH(cat.default_duration_h?.value ?? 4);
    }, (e) => setError(errorOf(e))).finally(() => { loading.current = false; });
  }, []);

  // Leaving the incident's session (or entering another) stops its cascade on the map.
  useEffect(() => { if (result && s.sid !== result.sid) setPlaying(null); }, [s.sid, result]);

  const launch = useCallback(async () => {
    const { s: cur, catalog: cat, selected: id, policy: pol, durationH: hours, busy: running } = live.current;
    const incident = cat?.incidents.find((x) => x.id === id);
    if (!incident || running) return;
    const plan = sessionPlan(cur.sid ? cur.session?.point ?? null : null, incident);
    if (plan === "replace" && !confirm(`Esto crea una sesión nueva a las ${pointText(incident.operating_point)} y sale de la sesión actual. ¿Seguir?`)) return;
    setBusy(true); setError(null); setPlaying(null); setResult(null);
    try {
      let sid = cur.sid;
      if (plan !== "reuse" || !sid) {
        const doc = await createSession({ point: incident.operating_point, label: `Incidente: ${incident.title}` });
        sid = doc.session_id;
        cur.join(sid); // the map enters the new session: network and state come from it
      }
      const run = await startIncidentRun(sid, { scenario: incident.id, policy: pol, duration_h: hours });
      const rid = String(run.run_id);
      const stepped = await stepRun(sid, rid, Number(run.horizon) || incident.horizon || 24);
      const [report, aar] = await Promise.all([getRunReport(sid, rid), getRunAfterAction(sid, rid)]);
      const snaps = (stepped.snapshots ?? []) as RunSnapshot[];
      const inc = (report.incident ?? {}) as { consequence_card?: IncidentCard };
      const card = inc.consequence_card;
      if (!card) throw new Error("La corrida no trajo la tarjeta de consecuencia.");
      setResult({
        sid, runId: rid, seed: typeof run.seed === "number" ? run.seed : null, incident, level: card.consequence_level, card,
        indicators: (report.indicators ?? {}) as Indicators, aar: (aar.incident ?? null) as IncidentAar | null,
        timeline: (aar.timeline ?? []) as AarCycle[], cascades: cascadeCycles(snaps), minutesPerCycle: cycleMinutes(snaps),
      });
    } catch (e) {
      setError(errorOf(e));
    } finally {
      setBusy(false);
    }
  }, []);

  const cascadeAt = useCallback((cycle: number) => result?.cascades.find((c) => c.cycle === cycle)?.timeline ?? null, [result]);
  return {
    catalog, selected, policy, durationH, busy, error, result, playing,
    load, select: setSelected, setPolicy, setDurationH, launch, cascadeAt,
    play: (cycle) => setPlaying(cycle),
    stop: () => setPlaying(null),
    close: () => { setPlaying(null); setResult(null); setError(null); },
  };
}

function errorOf(e: unknown): string {
  // A 5xx with no body is the dev proxy (or a gateway) failing to reach the backend.
  if (e instanceof ApiError && e.status >= 500 && e.status !== 503 && e.detail == null) return incidentError(null, `error ${e.status}`);
  if (e instanceof ApiError) return incidentError(e.status, e.message, e.retryAfter);
  return incidentError(e instanceof TypeError ? null : 0, (e as Error).message);
}
