import { describe, expect, it } from "vitest";
import type { Timeline } from "../cascade/types";
import { cardFigures, cascadeCycles, cycleMinutes, effectText, incidentTag, parseDuration, pointText, responseFigures, sessionPlan, type IncidentCard, type RunSnapshot } from "./incidents";

const tl = (label: string) => ({ scenario: label, label, failed_elements: [], truncated: false, duration_s: 10, events: [], frames: [{ t: 0 }], frequency_hz: {}, summary: {}, assumptions: [] }) as unknown as Timeline;
const card: IncidentCard = {
  incident: "polonia-2025", consequence_level: "L2", people_without_power: 3512405, load_shed_mw: 2028.5, unserved_energy_mwh: 8114.1,
  failure_cost_usd: 71322605, outage_duration_h: { value: 4, is_assumption: true }, note: "", notices: [],
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
    expect(effectText({ cycle: 2, type: "C1_generation_loss", target: "A01", params: { mw: 88.1 } })).toBe("Ciclo 2: Pérdida de generación en área A01 (88 MW)");
    expect(effectText({ cycle: 2, type: "C2_common_mode_loss", target: "NC", params: { share: 0.5, tech: "eolica" } })).toMatch(/Pérdida simultánea .* \(50 % de la eólica\)$/);
    expect(effectText({ cycle: 2, type: "C3_transmission_opening", target: "A06-A07", params: {} })).toBe("Ciclo 2: Apertura de transmisión en corredor A06-A07");
    expect(pointText("feb2025-1500")).toBe("feb. 2025, 15:00");
    expect(pointText("raro")).toBe("raro");
  });

  it("keeps only the cycles whose snapshot carries a cascade", () => {
    const snaps: RunSnapshot[] = [{ cycle: 1, t_min: 5, transient: null }, { cycle: 2, t_min: 10, transient: tl("a") }, { cycle: 3, t_min: 15 }, { cycle: 15, t_min: 75, transient: tl("b") }];
    expect(cascadeCycles(snaps).map((c) => [c.cycle, c.timeline.label])).toEqual([[2, "a"], [15, "b"]]);
    expect(cycleMinutes(snaps)).toBe(5);
    expect(cycleMinutes([])).toBe(5);
  });

  it("flags duration, MWh and cost as assumptions on the card", () => {
    const f = cardFigures(card);
    expect(f.map((x) => x.value)).toEqual(["3.512.405", "2.029", "8.114", "US$ 71,3 M"]);
    expect(f[2].tip).toContain("4 h supuestas (editable)");
    expect(f[3].tip).toContain("Supuesto");
  });

  it("labels the agentic response as experimental, with TTU in cycles and minutes", () => {
    const f = responseFigures({ mission_continuity: 0.8877, wrong_decisions: 2, operational_reserve: { final: 0.5972 }, situational_awareness: { time_to_understanding_cycles: 10, understood: true } }, 5);
    expect(f.map((x) => x.value)).toEqual(["10 ciclos · 50 min", "89 %", "2", "60 %"]);
    expect(f.every((x) => x.tip.includes("experimental"))).toBe(true);
    expect(responseFigures({ situational_awareness: { time_to_understanding_cycles: null, understood: false } }, 5)[0].value).toBe("no llegó a entender");
  });

  it("clamps the typed duration to what the API accepts", () => {
    expect(parseDuration("6,5")).toBe(6.5);
    expect(parseDuration("0.1")).toBe(0.25);
    expect(parseDuration("9999")).toBe(720);
    expect(parseDuration("")).toBeNull();
    expect(parseDuration("abc")).toBeNull();
  });
});
