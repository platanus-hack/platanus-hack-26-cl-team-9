import type { AfterAction, CacheIndex, CachedRun, Catalog, Narrative, Report, RunConfigIn, RunSummary, TheaterNetwork, TheaterSnapshot } from "./types";

/** One interface, two sources: the live API (new random runs, events, replay) or the precomputed runs offline. */
export interface TheaterSource {
  readonly live: boolean;
  network(point: string): Promise<TheaterNetwork>;
  catalog(): Promise<Catalog>;
  narrative(): Promise<Narrative>;
  create(cfg: RunConfigIn): Promise<RunSummary>;
  step(runId: string, cycles: number): Promise<{ run: RunSummary; snapshots: TheaterSnapshot[] }>;
  inject(runId: string, type: string, target: string): Promise<{ resolved_target: string; area: string | null }>;
  replay(runId: string, overrides: { policy?: string }): Promise<RunSummary>;
  snapshots(runId: string, start: number): Promise<TheaterSnapshot[]>;
  report(runId: string): Promise<Report>;
  afterAction(runId: string): Promise<AfterAction>;
}

const API = "/api/v1";

export class ApiError extends Error {}

async function call<T>(path: string, body?: unknown, fetcher: typeof fetch = fetch): Promise<T> {
  const r = await fetcher(`${API}${path}`, body === undefined ? undefined : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) {
    const detail = await r.json().then((j) => j.detail).catch(() => null);
    const msg = typeof detail === "string" ? detail : detail?.message ?? `Error ${r.status}`;
    throw new ApiError(msg);
  }
  return r.json() as Promise<T>;
}

export class LiveSource implements TheaterSource {
  readonly live = true;
  constructor(private fetcher: typeof fetch = fetch) {}
  network = (point: string) => call<TheaterNetwork>(`/sim/network?point=${encodeURIComponent(point)}`, undefined, this.fetcher);
  catalog = () => call<Catalog>("/sim/catalog", undefined, this.fetcher);
  narrative = () => call<Narrative>("/sim/narrative", undefined, this.fetcher);
  create = (cfg: RunConfigIn) => call<RunSummary>("/sim/runs", cfg, this.fetcher);
  step = (id: string, cycles: number) => call<{ run: RunSummary; snapshots: TheaterSnapshot[] }>(`/sim/runs/${id}/step`, { cycles }, this.fetcher);
  inject = (id: string, type: string, target: string) => call<{ resolved_target: string; area: string | null }>(`/sim/runs/${id}/events`, { type, target, cause: "intentional" }, this.fetcher);
  replay = (id: string, overrides: { policy?: string }) => call<RunSummary>(`/sim/runs/${id}/replay`, overrides, this.fetcher);
  snapshots = (id: string, start: number) => call<{ snapshots: TheaterSnapshot[] }>(`/sim/runs/${id}/snapshots?start=${start}`, undefined, this.fetcher).then((r) => r.snapshots);
  report = (id: string) => call<Report>(`/sim/runs/${id}/report`, undefined, this.fetcher);
  afterAction = (id: string) => call<AfterAction>(`/sim/runs/${id}/after_action`, undefined, this.fetcher);
}

/** Offline: plays the runs written by `cascadasen-sim-fixtures` in web/public/cache/theater, one cycle at a time. */
export class CachedSource implements TheaterSource {
  readonly live = false;
  private runs = new Map<string, { data: CachedRun; cursor: number }>();
  constructor(private fetcher: typeof fetch = fetch, private base = "/cache/theater") {}

  private async json<T>(path: string): Promise<T> {
    const r = await this.fetcher(`${this.base}/${path}`);
    if (!r.ok) throw new ApiError(`Sin servidor y sin corridas precalculadas (${path}). Genera la caché con cascadasen-sim-fixtures.`);
    return r.json() as Promise<T>;
  }

  index = () => this.json<CacheIndex>("index.json");
  network = (point: string) => this.json<TheaterNetwork>(`network-${point}.json`);
  catalog = () => this.json<Catalog>("catalog.json");
  narrative = () => this.json<Narrative>("narrative_es.json");

  async create(cfg: RunConfigIn): Promise<RunSummary> {
    const idx = await this.index();
    const hit = idx.runs.find((r) => r.point === cfg.point && r.policy === cfg.policy && r.template === cfg.template)
      ?? idx.runs.find((r) => r.point === cfg.point && r.policy === cfg.policy) ?? idx.runs.find((r) => r.point === cfg.point);
    if (!hit) throw new ApiError(`No hay una corrida precalculada para ${cfg.point}.`);
    const data = await this.json<CachedRun>(hit.file);
    const runId = `cache:${hit.file}`;
    this.runs.set(runId, { data, cursor: 0 });
    return { ...data.run, run_id: runId, status: "running", cycle: 0, t_min: 0 };
  }

  async step(runId: string, cycles: number) {
    const r = this.runs.get(runId);
    if (!r) throw new ApiError("Corrida desconocida");
    const snapshots = r.data.snapshots.slice(r.cursor, r.cursor + cycles);
    r.cursor += snapshots.length;
    const done = r.cursor >= r.data.snapshots.length;
    const last = snapshots.at(-1);
    return { run: { ...r.data.run, run_id: runId, status: done ? "finished" : "running", cycle: r.cursor, t_min: last ? last.t_min : 0 } as RunSummary, snapshots };
  }

  async inject(): Promise<{ resolved_target: string; area: string | null }> {
    throw new ApiError("Sin servidor no se pueden disparar eventos: es una corrida precalculada.");
  }

  async replay(runId: string, overrides: { policy?: string }): Promise<RunSummary> {
    const r = this.runs.get(runId);
    if (!r) throw new ApiError("Corrida desconocida");
    return this.create({ template: r.data.run.template, policy: overrides.policy ?? r.data.run.policy, point: r.data.run.operating_point });
  }

  async snapshots(runId: string, start: number) {
    const r = this.runs.get(runId);
    return r ? r.data.snapshots.slice(start, r.cursor) : [];
  }

  async report(runId: string) { return this.runs.get(runId)!.data.report; }
  async afterAction(runId: string) { return this.runs.get(runId)!.data.after_action; }
}

/** Live when the backend answers within the timeout, otherwise the offline cache. */
export async function connect(fetcher: typeof fetch = fetch, timeoutMs = 1500): Promise<TheaterSource> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetcher(`${API}/health`, { signal: ctrl.signal });
    if (r.ok) return new LiveSource(fetcher);
  } catch {
    // no backend: fall through to the cache
  } finally {
    clearTimeout(timer);
  }
  return new CachedSource(fetcher);
}
