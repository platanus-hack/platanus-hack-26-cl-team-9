import { useCallback, useEffect, useRef, useState } from "react";
import type { Timeline } from "../cascade/types";
import { ApiError, createSession, getIncidentCatalog, getRunAfterAction, getRunReport, getSimCatalog, startIncidentRun, stepRun } from "../session/sessionApi";
import type { Session } from "../session/useSession";
import { cascadeCycles, cycleMinutes, incidentError, pointText, sessionPlan, type AarCycle, type AreaNames, type CascadeCycle, type IncidentAar, type IncidentCard, type IncidentCatalog, type IncidentInfo, type Indicators, type Policy, type RunSnapshot } from "./incidents";

export interface IncidentResult {
  sid: string; runId: string; seed: number | null; incident: IncidentInfo; level: string; policy: Policy;
  card: IncidentCard; indicators: Indicators; aar: IncidentAar | null; timeline: AarCycle[]; cascades: CascadeCycle[]; minutesPerCycle: number;
}
export interface Incident {
  catalog: IncidentCatalog | null; areas: AreaNames; selected: string | null; policy: Policy; busy: boolean; error: string | null;
  result: IncidentResult | null; playing: number | null;
  load(): void; select(id: string): void; setPolicy(p: Policy): void;
  launch(): Promise<void>; play(cycle: number): void; stop(): void; close(): void; cascadeAt(cycle: number): Timeline | null;
}

/**
 * State of the Incidentes view (docs/mapa3.md section 4.2), owned by CascadeApp so the result survives view changes.
 * An incident runs at its own hour: without a session, or in one at another hour, `launch` creates a session at the
 * incident's point and joins it (after a confirmation when it leaves another session). Then it starts the run, steps
 * it to its horizon and reads the report and the after-action. `playing` is the cycle whose cascade the map plays: when
 * a run ends, the first cycle with a cascade plays by itself. The result keeps the policy that was submitted.
 */
export function useIncident(s: Session): Incident {
  const [catalog, setCatalog] = useState<IncidentCatalog | null>(null);
  const [areas, setAreas] = useState<AreaNames>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [policy, setPolicy] = useState<Policy>("C");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<IncidentResult | null>(null);
  const [playing, setPlaying] = useState<number | null>(null);
  const live = useRef({ s, catalog, selected, policy });
  live.current = { s, catalog, selected, policy };
  const loading = useRef(false);
  const launching = useRef(false); // set synchronously: a second activation in the same tick does not start a second run

  const load = useCallback(() => {
    if (live.current.catalog || loading.current) return;
    loading.current = true;
    setError(null);
    getIncidentCatalog().then((raw) => {
      setCatalog(raw as unknown as IncidentCatalog);
    }, (e) => setError(errorOf(e))).finally(() => { loading.current = false; });
    // Area names for the effects and the cycles; without them the codes stay.
    getSimCatalog().then((raw) => {
      const list = (raw.cyber_attack as { areas?: { id: string; name: string }[] } | undefined)?.areas ?? [];
      setAreas(Object.fromEntries(list.map((a) => [a.id, a.name])));
    }, () => undefined);
  }, []);

  // Leaving the incident's session (or entering another) stops its cascade on the map.
  useEffect(() => { if (result && s.sid !== result.sid) setPlaying(null); }, [s.sid, result]);

  const launch = useCallback(async () => {
    const { s: cur, catalog: cat, selected: id, policy: pol } = live.current;
    const incident = cat?.incidents.find((x) => x.id === id);
    if (!incident || launching.current) return;
    const plan = sessionPlan(cur.sid ? cur.session?.point ?? null : null, incident);
    if (plan === "replace" && !confirm(`Esto crea una sesión nueva a las ${pointText(incident.operating_point)} y sale de la sesión actual. ¿Seguir?`)) return;
    launching.current = true;
    setBusy(true); setError(null); setPlaying(null); setResult(null);
    try {
      let sid = cur.sid;
      if (plan !== "reuse" || !sid) {
        const doc = await createSession({ point: incident.operating_point, label: `Incidente: ${incident.title}` });
        sid = doc.session_id;
        cur.join(sid); // the map enters the new session: network and state come from it
      }
      const run = await startIncidentRun(sid, { scenario: incident.id, policy: pol });
      const rid = String(run.run_id);
      const stepped = await stepRun(sid, rid, Number(run.horizon) || incident.horizon || 24);
      const [report, aar] = await Promise.all([getRunReport(sid, rid), getRunAfterAction(sid, rid)]);
      const snaps = (stepped.snapshots ?? []) as RunSnapshot[];
      const inc = (report.incident ?? {}) as { consequence_card?: IncidentCard };
      const card = inc.consequence_card;
      if (!card) throw new Error("La simulación terminó sin la tarjeta de consecuencia.");
      const cascades = cascadeCycles(snaps);
      setResult({
        sid, runId: rid, seed: typeof run.seed === "number" ? run.seed : null, incident, level: card.consequence_level, card, policy: pol,
        indicators: (report.indicators ?? {}) as Indicators, aar: (aar.incident ?? null) as IncidentAar | null,
        timeline: (aar.timeline ?? []) as AarCycle[], cascades, minutesPerCycle: cycleMinutes(snaps),
      });
      if (cascades.length) setPlaying(cascades[0].cycle); // the map plays the first cascade by itself
    } catch (e) {
      setError(errorOf(e));
    } finally {
      launching.current = false;
      setBusy(false);
    }
  }, []);

  const cascadeAt = useCallback((cycle: number) => result?.cascades.find((c) => c.cycle === cycle)?.timeline ?? null, [result]);
  return {
    catalog, areas, selected, policy, busy, error, result, playing,
    load, select: (id) => { if (!launching.current) setSelected(id); }, setPolicy: (p) => { if (!launching.current) setPolicy(p); }, launch, cascadeAt,
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
