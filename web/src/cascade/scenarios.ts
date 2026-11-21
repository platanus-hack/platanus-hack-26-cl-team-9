/**
 * Starting cases of mapa 3: a base hour with or without a cut. Each one is a ready-made file in web/public/cache
 * (point id + line id), so picking one needs no computation in the browser.
 */
export interface Scenario { id: string; label: string; group: "base" | "cut"; point: string; cut: string | null }

/** R239 is Nueva Maitencillo - Nueva Pan de Azúcar 500 kV, the corridor that failed on 25 February 2025. */
export const CORRIDOR_25F = "R239";

/** R006 is Alto Jahuel - Ancoa 500 kV, the main south-to-center link. Cutting it at the evening peak starts a 5-stage cascade. */
export const ALTO_JAHUEL_ANCOA = "R006";

/** Named cut built by the cache builder (NAMED_CUTS): every line of S/E Charrúa open. File name `falla-charrua-2010.json` in each point folder. */
export const CHARRUA_2010 = "falla-charrua-2010";

export const SCENARIOS: Scenario[] = [
  { id: "dia-normal", label: "Día normal · febrero 2025, 15:00", group: "base", point: "feb2025-1500", cut: null },
  { id: "noche-normal", label: "Noche normal · febrero 2025, 03:00", group: "base", point: "feb2025-0300", cut: null },
  { id: "mediodia-solar-2026", label: "Mediodía solar · noviembre 2026, 13:00", group: "base", point: "nov2026-1300", cut: null },
  { id: "punta-2026", label: "Punta nocturna · noviembre 2026, 20:00", group: "base", point: "nov2026-2000", cut: null },
  { id: "25f", label: "Corte del 25F · febrero 2025, 15:00", group: "cut", point: "feb2025-1500", cut: CORRIDOR_25F },
  { id: "25f-noche", label: "Mismo corte de noche · febrero 2025, 03:00", group: "cut", point: "feb2025-0300", cut: CORRIDOR_25F },
  { id: "25f-2026", label: "Mismo corte con la red de 2026 · mediodía solar", group: "cut", point: "nov2026-1300", cut: CORRIDOR_25F },
  { id: "alto-jahuel-ancoa", label: "Corte Alto Jahuel – Ancoa 500 kV · punta nocturna 2026", group: "cut", point: "nov2026-2000", cut: ALTO_JAHUEL_ANCOA },
  { id: "charrua-2010", label: "Falla en S/E Charrúa · análogo del 14 mar 2010 · punta nocturna 2026", group: "cut", point: "nov2026-2000", cut: CHARRUA_2010 },
];

export const DEFAULT_SCENARIO = SCENARIOS[2];

/** The scenario that matches the current point and cut, or null when the user cut some other line. */
export function findScenario(point: string, cut: string | null): Scenario | null {
  return SCENARIOS.find((s) => s.point === point && s.cut === cut) ?? null;
}
