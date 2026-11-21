import { describe, expect, it } from "vitest";
import type { SessionNetwork } from "../cascade/types";
import { createLoader } from "./loader";
import type { CutState, SessionDoc } from "./sessionApi";

function deferred<T>() {
  let resolve!: (v: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}

/** Fake API: every call waits until the test resolves it; the calls of each route are kept in order. */
function setup() {
  const calls = { doc: [] as ReturnType<typeof deferred<SessionDoc>>[], net: [] as ReturnType<typeof deferred<SessionNetwork>>[], st: [] as ReturnType<typeof deferred<CutState>>[] };
  const shown: { doc: number[]; data: [number, number][] } = { doc: [], data: [] };
  const loader = createLoader({
    getSession: () => { const d = deferred<SessionDoc>(); calls.doc.push(d); return d.promise; },
    getNetwork: () => { const d = deferred<SessionNetwork>(); calls.net.push(d); return d.promise; },
    getState: () => { const d = deferred<CutState>(); calls.st.push(d); return d.promise; },
  }, {
    doc: (d) => shown.doc.push(d.revision),
    data: (n, st) => shown.data.push([n.dataset_revision, st.revision]),
  });
  return { calls, shown, loader };
}
const doc = (revision: number) => ({ revision }) as SessionDoc;
const net = (dataset_revision: number) => ({ dataset_revision }) as SessionNetwork;
const state = (revision: number) => ({ revision }) as CutState;

describe("createLoader", () => {
  it("keeps the network and state of a refresh that a document read overtakes", async () => {
    const { calls, shown, loader } = setup();
    const full = loader.load("s");          // dataset changed: refetch everything
    const run = loader.loadDoc("s");        // run event during the refresh
    calls.doc[1].resolve(doc(6));
    await run;
    calls.doc[0].resolve(doc(5)); calls.net[0].resolve(net(3)); calls.st[0].resolve(state(5));
    await full;
    expect(shown.data).toEqual([[3, 5]]);
    expect(shown.doc).toEqual([6]);         // the older document of the refresh is skipped
  });

  it("applies only the newest of two overlapping full loads", async () => {
    const { calls, shown, loader } = setup();
    const first = loader.load("s");
    const second = loader.load("s");
    calls.doc[1].resolve(doc(8)); calls.net[1].resolve(net(4)); calls.st[1].resolve(state(8));
    await second;
    calls.doc[0].resolve(doc(7)); calls.net[0].resolve(net(3)); calls.st[0].resolve(state(7));
    await first;
    expect(shown.data).toEqual([[4, 8]]);
    expect(shown.doc).toEqual([8]);
  });

  it("drops a load in flight after cancel", async () => {
    const { calls, shown, loader } = setup();
    const full = loader.load("s");
    loader.cancel();
    calls.doc[0].resolve(doc(1)); calls.net[0].resolve(net(1)); calls.st[0].resolve(state(1));
    await full;
    expect(shown).toEqual({ doc: [], data: [] });
  });
});
