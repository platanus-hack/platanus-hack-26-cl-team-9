import { describe, expect, it } from "vitest";
import type { Timeline } from "../cascade/types";
import { absorbed, cardFigures, cycleRows, dateText, incidentError, cascadeCycles, cycleMinutes, effectText, incidentTag, placeText, plainText, pointText, responseFigures, sessionPlan, sourceOf, type IncidentCard, type RunSnapshot } from "./incidents";

const tl = (label: string, shed = 100) => ({ scenario: label, label, failed_elements: [], truncated: false, duration_s: 10, events: [], frames: [{ t: 0 }], frequency_hz: {},
  summary: { load_shed_mw: shed, dark_buses: 0, lines_opened: [] }, assumptions: [] }) as unknown as Timeline;
const card: IncidentCard = {
  incident: "polonia-2025", consequence_level: "L2", people_without_power: 3512405, load_shed_mw: 2028.5, unserved_energy_mwh: 8114.1,
  failure_cost_usd: 17834910, cost_per_hour_usd: 17834910, outage_duration_h: { value: 1, is_assumption: true },
  cost_breakdown: { dark_mw: 0, shed_mw: 2029 },
  cost_basis: { blackout_restoration_h: { value: 7.34, source: "[44]", is_assumption: false }, shed_restoration_h: { value: 1, source: null, is_assumption: true } },
  note: "", notices: [],
};

describe("incidents", () => {
  it("plans the session: create without one, reuse at the same hour, replace at another", () => {
    const inc = { operating_point: "feb2025-1500" };
    expect(sessionPlan(null, inc)).toBe("create");
    expect(sessionPlan("feb2025-1500", inc)).toBe("reuse");
    expect(sessionPlan("nov2026-1300", inc)).toBe("replace");
  });

  it("tags references and unverified incidents, never ranks them", () => {
    expect(incidentTag({ kind: "reference_not_cyber", verified: true })).toBe("referencia, no es ciber");
    expect(incidentTag({ kind: "cyber_documented", verified: false })).toBe("no verificado");
    expect(incidentTag({ kind: "cyber_documented", verified: true })).toBeNull();
  });

  it("writes effects and points in Spanish", () => {
    const areas = { A01: "Arica–Iquique", A06: "Vallenar", A07: "La Serena–Coquimbo" };
    expect(effectText({ cycle: 2, type: "C1_generation_loss", target: "A01", params: { mw: 88.1 } }, areas)).toBe("Ciclo 2: Pérdida de generación en Arica–Iquique (88 MW)");
    expect(effectText({ cycle: 2, type: "C1_generation_loss", target: "A01", params: { mw: 88.1 } })).toBe("Ciclo 2: Pérdida de generación en el área A01 (88 MW)");
    expect(effectText({ cycle: 2, type: "C2_common_mode_loss", target: "NC", params: { share: 0.5, tech: "eolica" } })).toBe("Ciclo 2: Pérdida simultánea por zona y tecnología en la zona Norte Chico (50 % de la eólica)");
    expect(effectText({ cycle: 2, type: "C3_transmission_opening", target: "A06-A07", params: {} }, areas)).toBe("Ciclo 2: Apertura de transmisión en el corredor entre Vallenar y La Serena–Coquimbo");
    expect(pointText("feb2025-1500")).toBe("15:00 del 1 feb 2025");
    expect(pointText("nov2026-1300")).toBe("13:00 del 1 nov 2026");
    expect(pointText("raro")).toBe("raro");
    expect(dateText("2026-08-26")).toBe("26 ago 2026");
    expect(dateText("2025-02-01")).toBe("1 feb 2025");
    expect(dateText("pronto")).toBe("pronto");
    expect(placeText("A99", areas)).toBe("el área A99");
    expect(placeText("XX")).toBe("XX");
  });

  it("removes codes, reference numbers and file names from backend text", () => {
    const areas = { A06: "Vallenar", A07: "La Serena–Coquimbo", A09: "Santiago" };
    expect(plainText("Rearmar la defensa edac:centro_sur", areas)).toBe("Rearmar la defensa EDAC Centro-Sur");
    expect(plainText("Rearmar la defensa edac:norte_grande")).toBe("Rearmar la defensa EDAC Norte Grande");
    expect(plainText("Restablecer A06-A07", areas)).toBe("Restablecer el corredor entre Vallenar y La Serena–Coquimbo");
    expect(plainText("Reforzar la vigilancia de A09", areas)).toBe("Reforzar la vigilancia de Santiago");
    expect(plainText("Pérdida simultánea por zona y tecnología en NC")).toBe("Pérdida simultánea por zona y tecnología en la zona Norte Chico");
    expect(plainText("La batería informada no aparece en storage.geojson: no se modela.")).toBe("La batería informada no aparece en los datos del modelo: no se modela.");
    expect(plainText("calibrado con el 25F [44], CNE [19].")).toBe("calibrado con el 25F, CNE.");
    expect(plainText("el mismo de Estado de la red")).toBe("el mismo de la pestaña Cambios");
  });

  it("names repository sources for people and keeps the others", () => {
    expect(sourceOf({ label: "docs/idea.md [3]", url: "docs/idea.md" })).toEqual({ label: "Informe del Coordinador Eléctrico Nacional sobre el 25F", url: expect.stringMatching(/^https:\/\/www\.coordinador\.cl\//) });
    const press = { label: "T13", url: "https://www.t13.cl/x" };
    expect(sourceOf(press)).toBe(press);
  });

  it("keeps only the cycles whose snapshot carries a visible cascade", () => {
    const snaps: RunSnapshot[] = [{ cycle: 1, t_min: 5, transient: null }, { cycle: 2, t_min: 10, transient: tl("a") }, { cycle: 3, t_min: 15 }, { cycle: 4, t_min: 20, transient: tl("stable island", 0) }, { cycle: 15, t_min: 75, transient: tl("b") }];
    expect(cascadeCycles(snaps).map((c) => [c.cycle, c.timeline.label])).toEqual([[2, "a"], [15, "b"]]);
    expect(cycleMinutes(snaps)).toBe(5);
    expect(cycleMinutes([])).toBe(5);
    const rows = cycleRows([{ cycle: 2, t_min: 10, lines: ["x"] }, { cycle: 20, t_min: 100, lines: ["y"] }], cascadeCycles(snaps));
    expect(rows.map((r) => r.cycle)).toEqual([2, 15, 20]);
  });

  it("explains where MWh and cost come from: the engine's calibrated method, with the assumed hour flagged", () => {
    const f = cardFigures(card);
    expect(f.map((x) => x.value)).toEqual(["3.512.405", "2.029", "8.114", "US$ 17,8 M"]);
    expect(f.map((x) => x.label)).toEqual(["personas sin suministro", "MW de carga perdida", "MWh no servidos", "costo de falla"]);
    expect(f[2].tip).toContain("pestaña de cambios");
    expect(f[2].tip).toContain("1 h (supuesto)");
    expect(f[3].tip).toContain("7,34 h de arranque en negro, calibradas con el 25F");
    expect(f.every((x) => !/\[\d+\]|report\.|\.md/.test(x.tip))).toBe(true);
    expect(f[3].tip).toContain("el corte de carga paga 1 h (supuesto)");
  });

  it("labels the hours of a total blackout as calibrated, not assumed", () => {
    const blackout = { ...card, outage_duration_h: { value: 7.34, is_assumption: false } };
    expect(cardFigures(blackout)[2].tip).toContain("7,34 h (calibrado con el 25F)");
    expect(absorbed(card)).toBe(false);
    expect(absorbed({ ...card, consequence_level: "L0", people_without_power: 0, load_shed_mw: 0 })).toBe(true);
  });

  it("labels the agentic response as experimental, with TTU in cycles and minutes", () => {
    const f = responseFigures({ mission_continuity: 0.8877, wrong_decisions: 2, operational_reserve: { final: 0.5972 }, situational_awareness: { time_to_understanding_cycles: 10, understood: true } }, 5);
    expect(f.map((x) => x.value)).toEqual(["10 ciclos · 50 min", "89 %", "2", "60 %"]);
    expect(f.every((x) => x.tip.includes("experimental"))).toBe(true);
    const none = responseFigures({ situational_awareness: { time_to_understanding_cycles: null, understood: false } }, 5)[0];
    expect(none).toMatchObject({ value: "no se identificó en el horizonte", text: true });
  });

  it("explains failures in Spanish", () => {
    expect(incidentError(null, "Failed to fetch")).toBe("No se pudo conectar con el servidor.");
    expect(incidentError(429, "x", 7)).toContain("espera 7 s");
    expect(incidentError(503, "x")).toContain("no puede simular ahora");
    expect(incidentError(422, "el incidente corre a las feb2025-1500")).toContain("feb2025-1500");
  });
});
