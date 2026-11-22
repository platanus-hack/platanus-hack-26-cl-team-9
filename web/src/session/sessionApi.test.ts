import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { addElement, ApiError, cutLines, deleteElement, getIncidentCatalog, getNetwork, sessionIdFrom, startIncidentRun, subscribe, updateElement } from "./sessionApi";

const SID = "abcdefghijklmnopqrstuv";
const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(status === 304 ? null : JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

describe("sessionApi", () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  beforeEach(() => { fetchMock = vi.fn(); vi.stubGlobal("fetch", fetchMock); });
  afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

  it("takes the session only from ?sesion= and ignores malformed ids", () => {
    expect(sessionIdFrom(`?sesion=${SID}&point=nov2026-1300`)).toBe(SID);
    expect(sessionIdFrom("")).toBeNull();
    expect(sessionIdFrom("?sesion=../x")).toBeNull();
    expect(sessionIdFrom("?point=nov2026-1300")).toBeNull();
  });

  it("sends method, path, body, If-Match and X-Sub50-Agent", async () => {
    fetchMock.mockResolvedValue(json(201, { id: "D001", revision: 4, warnings: [], balance: [] }));
    const out = await addElement(SID, "loads", { bus: "B010", mw: 120, kind: "datacenter", name: "DC" }, 3);
    expect(out.id).toBe("D001");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`/api/v1/sessions/${SID}/loads`);
    expect(init.method).toBe("POST");
    expect(init.headers).toMatchObject({ "If-Match": '"3"', "X-Sub50-Agent": "web", "Content-Type": "application/json" });
    expect(JSON.parse(init.body)).toEqual({ bus: "B010", mw: 120, kind: "datacenter", name: "DC" });
  });

  it("builds element, cut and read routes", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(json(200, {})));
    await updateElement(SID, "lines", "U001", { capacity_mw: 450 });
    await deleteElement(SID, "buses", "B188", 7);
    await cutLines(SID, ["R014"]);
    await getNetwork(SID);
    const calls = fetchMock.mock.calls.map(([url, init]) => `${init.method} ${url}`);
    expect(calls).toEqual([`PATCH /api/v1/sessions/${SID}/lines/U001`, `DELETE /api/v1/sessions/${SID}/buses/B188`, `POST /api/v1/sessions/${SID}/cut`, `GET /api/v1/sessions/${SID}/network`]);
    expect(fetchMock.mock.calls[0][1].headers["If-Match"]).toBeUndefined();
    expect(fetchMock.mock.calls[1][1].headers["If-Match"]).toBe('"7"');
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ lines: ["R014"] });
  });

  it("reads the incident catalog outside /sessions and launches an incident inside the session", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(json(200, {})));
    await getIncidentCatalog();
    await startIncidentRun(SID, { scenario: "huatacondo-2026", policy: "C", duration_h: 6 });
    const calls = fetchMock.mock.calls.map(([url, init]) => `${init.method} ${url}`);
    expect(calls).toEqual(["GET /api/v1/attacks/catalog", `POST /api/v1/sessions/${SID}/attacks/runs`]);
    expect(fetchMock.mock.calls[0][1].headers["X-Sub50-Agent"]).toBe("web");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ scenario: "huatacondo-2026", policy: "C", duration_h: 6 });
  });

  it("raises ApiError with the status and the Spanish message", async () => {
    fetchMock.mockResolvedValue(json(422, { detail: { field: "U001.b", message: "Una línea necesita dos barras distintas." } }));
    const err = await addElement(SID, "lines", { a: "B010", b: "B010", kv: 220, capacity_mw: 100 }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.message).toBe("Una línea necesita dos barras distintas.");
  });

  it("retries a busy 409 after Retry-After, up to 2 times, with the same request", async () => {
    vi.useFakeTimers();
    const busy = () => json(409, { detail: "La sesión está ocupada con otra solicitud; reintenta." }, { "Retry-After": "1" });
    fetchMock.mockResolvedValueOnce(busy()).mockResolvedValueOnce(busy()).mockResolvedValueOnce(json(200, { revision: 5, open_lines: ["R014"] }));
    const out = cutLines(SID, ["R014"], 3);
    await vi.advanceTimersByTimeAsync(999);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1001);
    expect((await out).revision).toBe(5);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    for (const [url, init] of fetchMock.mock.calls) {
      expect(`${init.method} ${url}`).toBe(`POST /api/v1/sessions/${SID}/cut`);
      expect(init.headers["If-Match"]).toBe('"3"');
      expect(JSON.parse(init.body)).toEqual({ lines: ["R014"] });
    }
  });
  it("gives up on a session still busy after 2 retries and does not retry a 409 without Retry-After", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementation(() => Promise.resolve(json(409, { detail: "La sesión está ocupada con otra solicitud; reintenta." }, { "Retry-After": "1" })));
    const busy = getNetwork(SID).catch((e) => e);
    await vi.advanceTimersByTimeAsync(5000);
    const err = await busy;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(json(409, { detail: "La sesión cambió en otra instancia; reintenta" }));
    expect((await deleteElement(SID, "loads", "D001", 2).catch((e) => e)).status).toBe(409);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("polls GET /{sid} with If-None-Match when EventSource is undefined", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("EventSource", undefined);
    const doc = (revision: number) => ({ revision, last_op: { op: "load_added", ids: ["D001"], by: "bot-1", revision } });
    fetchMock
      .mockResolvedValueOnce(json(200, doc(1), { ETag: '"1"' }))
      .mockResolvedValueOnce(json(304, null, { ETag: '"1"' }))
      .mockResolvedValueOnce(json(200, doc(2), { ETag: '"2"' }));
    const seen: number[] = [];
    const sub = subscribe(SID, (e) => seen.push(e.revision), { pollMs: 2000 });
    expect(sub.mode).toBe("poll");
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(2000);
    await vi.advanceTimersByTimeAsync(2000);
    sub.close();
    await vi.advanceTimersByTimeAsync(4000);
    expect(seen).toEqual([1, 2]);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock.mock.calls[0][1].headers["If-None-Match"]).toBeUndefined();
    expect(fetchMock.mock.calls[1][0]).toBe(`/api/v1/sessions/${SID}`);
    expect(fetchMock.mock.calls[1][1].headers["If-None-Match"]).toBe('"1"');
    expect(fetchMock.mock.calls[2][1].headers["If-None-Match"]).toBe('"1"');
  });

  it("stops polling and reports a session that is gone", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("EventSource", undefined);
    fetchMock.mockResolvedValue(json(404, { detail: "Sesión desconocida." }));
    const gone = vi.fn();
    subscribe(SID, () => undefined, { onGone: gone });
    await vi.advanceTimersByTimeAsync(6000);
    expect(gone).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
