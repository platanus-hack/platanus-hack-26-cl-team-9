import type { SessionNetwork } from "../cascade/types";
import type { CutState, SessionDoc } from "./sessionApi";

export interface LoaderApi {
  getSession(id: string): Promise<SessionDoc>;
  getNetwork(id: string): Promise<SessionNetwork>;
  getState(id: string): Promise<CutState>;
}
export interface LoaderApply { doc(d: SessionDoc): void; data(n: SessionNetwork, st: CutState): void }

/**
 * Decides which refetch result reaches the screen. A full load applies network and state when it is the newest full
 * load, and its session document only when no newer document read started; a document read applies only when it is
 * the newest one. So a run event (document read) during a dataset refresh keeps the refresh's network and state.
 */
export function createLoader(api: LoaderApi, apply: LoaderApply) {
  let seq = 0;    // newest full load
  let docSeq = 0; // newest document read (full loads read the document too)
  return {
    async load(id: string) {
      const mine = ++seq, mineDoc = ++docSeq;
      const [doc, net, st] = await Promise.all([api.getSession(id), api.getNetwork(id), api.getState(id)]);
      if (mine !== seq) return;
      apply.data(net, st);
      if (mineDoc === docSeq) apply.doc(doc);
    },
    async loadDoc(id: string) {
      const mine = ++docSeq;
      const doc = await api.getSession(id);
      if (mine === docSeq) apply.doc(doc);
    },
    cancel() { seq++; docSeq++; },
  };
}
