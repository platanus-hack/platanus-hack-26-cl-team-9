import { describe, expect, it } from "vitest";
import { areaOrder, CREWS, defaultTexts, eventText, FIELDS, frameFigures, frames, invalidFields, OUTCOME_LABEL, parseField, readForm, runBody, SEED, shown, stored, type CyberCatalog, type CyberFrame } from "./cyber";

const cat: CyberCatalog = {
  template: "ciberataque", defaults: { spread_p: 0.45, strike_delay: 2, spread_cooldown: 3 }, bounds: { spread_p: [0, 1], strike_delay: [0, 12], spread_cooldown: [1, 12] },
  outcomes: ["attack", "defense", "undecided"], crews_default: 9, adjacency: { A01: ["A02"] }, areas: [], is_assumption: true,
};

describe("cyber", () => {
  it("sends only the changed parameters and maps the LLM defence to llm_commander", () => {
    const body = runBody(cat, { spread_p: 0.6, strike_delay: 2 }, "llm", 4, 7);
    expect(body).toMatchObject({ template: "ciberataque", policy: "C", llm_commander: true, capabilities: { field_crews: 4 }, seed: 7 });
    expect(body.adversary).toMatchObject({ mode: "propagation", propagation: { spread_p: 0.6 } });
    const plain = runBody(cat, { ...cat.defaults }, "A", 9, null);
    expect(plain.policy).toBe("A");
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

  it("keeps typed text as is and checks it against the catalog bounds in display units", () => {
    const cool = FIELDS.find((f) => f.key === "spread_cooldown")!;
    const spread = FIELDS.find((f) => f.key === "spread_p")!;
    expect(parseField(cool, "2,5", cat)).toEqual({ value: null, error: "Espera entre saltos: entre 1 y 12 ciclos, sin decimales" });
    expect(parseField(cool, "", cat).error).toBe("Espera entre saltos: entre 1 y 12 ciclos, sin decimales");
    expect(parseField(cool, "0", cat).error).not.toBeNull();
    expect(parseField(cool, "13", cat).error).not.toBeNull();
    expect(parseField(cool, "-1", cat).error).not.toBeNull();
    expect(parseField(cool, "abc", cat).error).not.toBeNull();
    expect(parseField(cool, " 4 ", cat)).toEqual({ value: 4, error: null });
    expect(parseField(spread, "62,5", cat)).toEqual({ value: 0.625, error: null });
    expect(parseField(spread, "101", cat).error).toBe("Probabilidad de salto a un vecino: entre 0 y 100 %");
    expect(parseField(CREWS, "61", cat).error).toBe("Cuadrillas de terreno: entre 0 y 60, sin decimales");
    expect(parseField(SEED, "", cat)).toEqual({ value: null, error: null });
    expect(parseField(SEED, "12", cat)).toEqual({ value: 12, error: null });
    expect(parseField(SEED, "1,5", cat).error).toMatch(/^Semilla: /);
  });

  it("starts from the catalog defaults and reads the whole form into a run body or per-field errors", () => {
    const texts = defaultTexts(cat);
    expect(texts).toEqual({ spread_p: "45", strike_delay: "2", spread_cooldown: "3", field_crews: "9", seed: "" });
    expect(readForm(cat, texts)).toEqual({ params: { spread_p: 0.45, strike_delay: 2, spread_cooldown: 3 }, crews: 9, seed: null, errors: {} });
    const bad = readForm(cat, { ...texts, spread_cooldown: "", field_crews: "4", seed: "77" });
    expect(Object.keys(bad.errors)).toEqual(["spread_cooldown"]);
    expect(bad.crews).toBe(4);
    expect(bad.seed).toBe(77);
  });

  it("lists affected areas first and keeps the catalog order inside each state", () => {
    const areas = [{ id: "A01" }, { id: "A02" }, { id: "A03" }, { id: "A04" }];
    expect(areaOrder(areas, { A01: "clean", A02: "eradicated", A03: "struck", A04: "compromised" }).map((a) => a.id)).toEqual(["A03", "A04", "A02", "A01"]);
    expect(areaOrder(areas, {}).map((a) => a.id)).toEqual(["A01", "A02", "A03", "A04"]);
  });

  it("says what happened to the network, never who won, and marks every figure as a model value", () => {
    expect(Object.values(OUTCOME_LABEL)).toEqual(["La red perdió el umbral de demanda", "La defensa contuvo la intrusión y reparó todo", "Sin desenlace al terminar el horizonte"]);
    const f = { cycle: 1, t_min: 5, areas: {}, counts: { clean: 10, compromised: 1, struck: 2, eradicated: 0 }, outcome: null, lost_share: 0.12, people_without_power: 1234, crews_busy: 2, events: [], transient: null } as CyberFrame;
    const figs = frameFigures(f);
    expect(figs.map((x) => [x.label, x.value])).toEqual([["áreas con intrusión", "3"], ["áreas recuperadas", "0"], ["demanda sin suministro", "12 %"], ["personas sin suministro", "1.234"]]);
    expect(figs.every((x) => x.tip.includes("Valor del modelo"))).toBe(true);
  });
});
