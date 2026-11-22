import { describe, expect, it } from "vitest";
import { eventText, frames, invalidFields, runBody, shown, stored, type CyberCatalog } from "./cyber";

const cat: CyberCatalog = {
  template: "ciberataque", defaults: { spread_p: 0.45, strike_delay: 2 }, bounds: { spread_p: [0, 1], strike_delay: [0, 12] },
  outcomes: ["attack", "defense", "undecided"], crews_default: 9, adjacency: { A01: ["A02"] }, areas: [], is_assumption: true,
};

describe("cyber", () => {
  it("sends only the changed parameters and maps the LLM defence to llm_commander", () => {
    const body = runBody(cat, { spread_p: 0.6, strike_delay: 2 }, "llm", 4, 7);
    expect(body).toMatchObject({ template: "ciberataque", policy: "C", llm_commander: true, capabilities: { field_crews: 4 }, seed: 7 });
    expect(body.adversary).toMatchObject({ mode: "propagation", propagation: { spread_p: 0.6 } });
    const plain = runBody(cat, { ...cat.defaults }, "A", 9, null);
    expect(plain.adversary).not.toHaveProperty("propagation");
    expect(plain).not.toHaveProperty("seed");
    expect(plain.llm_commander).toBe(false);
  });

  it("flags values outside the catalog bounds", () => {
    expect(invalidFields(cat, { spread_p: 1.5, strike_delay: 2 })).toEqual(["spread_p"]);
    expect(invalidFields(cat, { spread_p: Number.NaN })).toEqual(["spread_p"]);
  });

  it("keeps only snapshots with a cyber block", () => {
    const cyber = { areas: {}, counts: { clean: 1, compromised: 0, struck: 0, eradicated: 0 }, outcome: null, lost_share: 0, people_without_power: 0, crews_busy: 0, events: [] };
    expect(frames([{ cycle: 0, t_min: 0 }, { cycle: 1, t_min: 5, cyber }])).toEqual([{ ...cyber, cycle: 1, t_min: 5, transient: null }]);
  });

  it("writes events in Spanish with area names", () => {
    const name = (id: string) => ({ A01: "Arica", A02: "Crucero" })[id] ?? id;
    expect(eventText({ cycle: 3, kind: "compromised", area: "A02", from: "A01" }, name)).toBe("La intrusión salta de Arica a Crucero.");
    expect(eventText({ cycle: 3, kind: "blocked", area: "A02", from: "A01" }, name)).toMatch(/frena/);
  });

  it("shows probabilities as percent and cycles as they are", () => {
    expect(shown("prob", 0.45)).toBe(45);
    expect(stored("prob", 45)).toBe(0.45);
    expect(shown("ciclos", 3)).toBe(3);
  });
});
