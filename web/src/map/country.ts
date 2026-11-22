/** ISO 3166-1 alpha-3 of the network the engine simulates. Elements without `country` (older caches) are Chile's. */
export const DEFAULT_COUNTRY = "CHL";
/** Network ids of uploaded networks: `upload:<id>`. Built-in networks use their ISO3 as id. */
export const UPLOAD_PREFIX = "upload:";

/** Why: one place reads the field, so a cache published before the field existed still reads as Chile (issue #49). */
export function countryOf(element: { country?: string | null } | null | undefined): string {
  return element?.country || DEFAULT_COUNTRY;
}

export interface NetworkInfo {
  id: string;
  country: string;
  name: string;
  /** Second part of the panel header ("Sistema Eléctrico Nacional"). */
  system: string;
  /** Only Chile has the electrical data the engine needs (docs/network-format.md section 2: level L2). */
  simulable: boolean;
  uploaded: boolean;
}

/** The five networks shipped with the app: Chile (engine) and the drawn layers of docs/regional.md. */
export const BUILT_IN: NetworkInfo[] = [
  { id: "CHL", country: "CHL", name: "Chile", system: "Sistema Eléctrico Nacional", simulable: true, uploaded: false },
  { id: "ARG", country: "ARG", name: "Argentina", system: "Sistema Argentino de Interconexión", simulable: false, uploaded: false },
  { id: "BOL", country: "BOL", name: "Bolivia", system: "Sistema Interconectado Nacional", simulable: false, uploaded: false },
  { id: "BRA", country: "BRA", name: "Brasil", system: "Sistema Interligado Nacional", simulable: false, uploaded: false },
  { id: "PER", country: "PER", name: "Perú", system: "Sistema Eléctrico Interconectado Nacional", simulable: false, uploaded: false },
];

export const VIEW_ONLY = "Esta red es solo para ver: no tiene los datos eléctricos que necesita la simulación (reactancia, capacidad, demanda e inercia).";

/** `?pais=PER` opens Peru; anything else (missing, unknown, lowercase typos) falls back to Chile. */
export function networkFromParam(value: string | null, available: string[]): string {
  const iso = (value ?? "").trim().toUpperCase();
  return available.includes(iso) ? iso : DEFAULT_COUNTRY;
}

export const isUpload = (id: string) => id.startsWith(UPLOAD_PREFIX);
