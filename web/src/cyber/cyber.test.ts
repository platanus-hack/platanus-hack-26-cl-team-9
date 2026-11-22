import { describe, expect, it } from "vitest";
import { actionText, activePreset, eventText, frames, invalidFields, runBody, scoreboard, shown, statusOf, stored, type CyberCatalog, type CyberFrame } from "./cyber";

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

  it("lets the user defend by hand with manual_defense", () => {
    const body = runBody(cat, { ...cat.defaults }, "user", 9, null);
    expect(body).toMatchObject({ manual_defense: true, llm_commander: false, policy: "C" });
    expect(runBody(cat, { ...cat.defaults }, "B", 9, null)).toMatchObject({ manual_defense: false, policy: "B" });
  });

  it("reads each area's side and the two counters", () => {
    const f = {
      cycle: 3, t_min: 15, areas: { A01: "struck", A02: "compromised", A03: "clean", A04: "eradicated", A05: "clean" },
      counts: { clean: 2, compromised: 1, struck: 1, eradicated: 1 }, outcome: null, lost_share: 0.1, people_without_power: 250000,
      crews_busy: 2, events: [], transient: null, dark: ["A03"], segmented: ["A05"],
    } as unknown as CyberFrame;
    expect(["A01", "A02", "A03", "A04", "A05"].map((id) => statusOf(f, id))).toEqual(["struck", "compromised", "dark", "recovered", "shielded"]);
    expect(statusOf(f, "A02", true)).toBe("clean"); // a latent intrusion is hidden from a user defending
    expect(statusOf({ ...f, segmented: ["A01"] }, "A01")).toBe("compromised"); // hit and segmented: both sides on it
    const areas = ["A01", "A02", "A03", "A04", "A05"].map((id, i) => ({ id, name: id, zone: "NG", population: (i + 1) * 100000, lon: 0, lat: 0 }));
    expect(scoreboard(f, areas)).toEqual({ attackAreas: 2, disputed: 1, peopleOut: 250000, defenseAreas: 2, protectedPeople: 900000 });
  });

  it("says why a defence action failed", () => {
    expect(actionText({ action: "restore_element", target: "A01", ok: false, verdict: "no_crew_in_range" }, (x) => x)).toMatch(/ninguna cuadrilla/);
    expect(actionText({ action: "digital_segmentation", target: "A01", ok: true }, (x) => x)).toBe("La defensa segmenta A01.");
  });

  it("finds the preset the form holds, and none after a manual edit", () => {
    const withPresets = { ...cat, presets: [{ id: "facil", label: "Fácil", params: { spread_p: 0.35 } }] };
    expect(activePreset(withPresets, { spread_p: 0.35, strike_delay: 2 })?.id).toBe("facil");
    expect(activePreset(withPresets, { spread_p: 0.4, strike_delay: 2 })).toBeNull();
  });
});
