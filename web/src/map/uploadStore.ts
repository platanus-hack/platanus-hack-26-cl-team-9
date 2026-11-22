import type { RegionalGrid } from "./regional";

/** An uploaded network, kept only in this browser (issue #49 part C: no server, sharing waits for #34 and #44). */
export interface StoredNetwork { id: string; name: string; country: string; grid: RegionalGrid; savedAt: string }

// IndexedDB, not localStorage: a 10 MB file does not fit localStorage's usual 5 MB.
const DB = "sub50";
const STORE = "uploaded-networks";

function _open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") return reject(new Error("Este navegador no guarda datos locales."));
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => { if (!req.result.objectStoreNames.contains(STORE)) req.result.createObjectStore(STORE, { keyPath: "id" }); };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("No se pudo abrir el almacenamiento local."));
  });
}

async function _run<T>(mode: IDBTransactionMode, work: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await _open();
  try {
    return await new Promise<T>((resolve, reject) => {
      const req = work(db.transaction(STORE, mode).objectStore(STORE));
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error ?? new Error("Falló el almacenamiento local."));
    });
  } finally {
    db.close();
  }
}

/** Every stored network, oldest first. Fails (rejects) in a private window or with site data blocked; callers catch it. */
export async function listUploads(): Promise<StoredNetwork[]> {
  const all = await _run<StoredNetwork[]>("readonly", (s) => s.getAll() as IDBRequest<StoredNetwork[]>);
  return all.sort((a, b) => a.savedAt.localeCompare(b.savedAt));
}

export const saveUpload = (n: StoredNetwork) => _run("readwrite", (s) => s.put(n)).then(() => undefined);
export const deleteUpload = (id: string) => _run("readwrite", (s) => s.delete(id)).then(() => undefined);

export function newUploadId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`;
}
