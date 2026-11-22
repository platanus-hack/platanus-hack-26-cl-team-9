// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Timeline } from "../cascade/types";
import { NOTICES, type IncidentInfo } from "./incidents";
import { IncidentPanel } from "./IncidentPanel";
import type { Incident, IncidentResult } from "./useIncident";

afterEach(cleanup);
// jsdom has no layout: the result scrolls its heading into view on mount.
Element.prototype.scrollIntoView = vi.fn();

const info = (over: Partial<IncidentInfo> = {}): IncidentInfo => ({
  id: "huatacondo-2026", title: "Huatacondo", date: "2026-08-26", kind: "cyber_documented", verified: true,
  sources: [{ label: "Fuente uno", url: "https://example.org/uno" }], notes: ["Nota del catálogo"], mitigations: [],
  operating_point: "nov2026-1300", horizon: 24, effects: [{ cycle: 2, type: "C1_generation_loss", target: "A01", params: { mw: 88.1 } }], ...over,
});
const catalog = { notices: [], cost_basis: {}, incidents: [info(), info({ id: "polonia-2025", title: "Polonia", kind: "reference_not_cyber", operating_point: "feb2025-1500" })] };

function incident(over: Partial<Incident> = {}): Incident {
  return {
    catalog: null, areas: { A01: "Arica–Iquique" }, selected: null, policy: "C", busy: false, error: null, result: null, playing: null,
    load: vi.fn(), select: vi.fn(), setPolicy: vi.fn(), launch: vi.fn(async () => {}), play: vi.fn(), stop: vi.fn(), close: vi.fn(), cascadeAt: () => null, ...over,
  };
}
const result: IncidentResult = {
  sid: "s1", runId: "r1", seed: 7, incident: info(), level: "L2", policy: "A", minutesPerCycle: 5,
  card: {
    incident: "huatacondo-2026", consequence_level: "L2", people_without_power: 3_512_405, load_shed_mw: 2028.5, unserved_energy_mwh: 8114.1,
    failure_cost_usd: 17_834_910, cost_per_hour_usd: 17_834_910, outage_duration_h: { value: 1, is_assumption: true }, cost_breakdown: {}, cost_basis: {},
    note: "Nota de la tarjeta.", notices: [],
  },
  indicators: { mission_continuity: 0.8, situational_awareness: { time_to_understanding_cycles: 2, understood: true } },
  aar: { title: "Huatacondo", summary: "Resumen del incidente.", effect: "", prevention: ["Segmentar la red"], notes: ["Nota del informe"], sources: [{ label: "Fuente informe", url: "https://example.org/aar" }], verified: true, notices: [] },
  timeline: [{ cycle: 1, t_min: 5, lines: ["Sin novedades"] }, { cycle: 2, t_min: 10, lines: ["Se pierde generación en A01"] }, { cycle: 4, t_min: 20, lines: ["Rearmar la defensa edac:centro_sur"] }],
  cascades: [{ cycle: 2, t_min: 10, timeline: {} as Timeline }],
};

describe("IncidentPanel: the catalog", () => {
  it("loads the catalog on mount, says it is loading and shows both notices", () => {
    const inc = incident();
    render(<IncidentPanel inc={inc} sessionPoint={null} />);
    expect(inc.load).toHaveBeenCalledOnce();
    expect(screen.getByText("Cargando el catálogo…")).toBeTruthy();
    expect(screen.getByText(NOTICES[0], { exact: false })).toBeTruthy();
    expect(screen.getByText(NOTICES[1], { exact: false })).toBeTruthy();
  });

  it("shows the error with a retry instead of the loading text when the catalog fails", () => {
    const inc = incident({ error: "No se pudo conectar con el servidor." });
    render(<IncidentPanel inc={inc} sessionPoint={null} />);
    expect(screen.getByRole("alert").textContent).toContain("No se pudo conectar con el servidor.");
    expect(screen.queryByText("Cargando el catálogo…")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(inc.load).toHaveBeenCalledTimes(2); // on mount and on retry
  });

  it("lists the incidents in file order with their date, hour and tag, and selects one", () => {
    const inc = incident({ catalog });
    render(<IncidentPanel inc={inc} sessionPoint={null} />);
    const radios = screen.getAllByRole("radio");
    expect(radios.map((r) => r.querySelector(".inc-title")?.textContent)).toEqual(["Huatacondo", "Polonia"]);
    expect(radios[0].textContent).toContain("26 ago 2026 · simulado a las 13:00 del 1 nov 2026");
    expect(screen.getByText("referencia, no es ciber")).toBeTruthy();
    expect(screen.queryByText(/Pérdida de generación/)).toBeNull(); // effects only on the selected card
    fireEvent.click(radios[1]);
    expect(inc.select).toHaveBeenCalledWith("polonia-2025");
  });

  it("marks the selected card, shows its effects with area names and moves the selection with the arrow keys", () => {
    const inc = incident({ catalog, selected: "huatacondo-2026" });
    render(<IncidentPanel inc={inc} sessionPoint={null} />);
    const radios = screen.getAllByRole("radio");
    expect(radios.map((r) => r.getAttribute("aria-checked"))).toEqual(["true", "false"]);
    expect(radios.map((r) => r.tabIndex)).toEqual([0, -1]);
    expect(screen.getByText("Ciclo 2: Pérdida de generación en Arica–Iquique (88 MW)")).toBeTruthy();
    fireEvent.keyDown(radios[0], { key: "ArrowDown" });
    expect(inc.select).toHaveBeenCalledWith("polonia-2025");
  });

  it("keeps the launch button off until an incident is chosen, then launches", () => {
    const { unmount } = render(<IncidentPanel inc={incident({ catalog })} sessionPoint={null} />);
    expect((screen.getByRole("button", { name: "Simular incidente" }) as HTMLButtonElement).disabled).toBe(true);
    unmount();
    const inc = incident({ catalog, selected: "huatacondo-2026" });
    render(<IncidentPanel inc={inc} sessionPoint="nov2026-1300" />);
    expect(screen.getByText("Se simula en la sesión actual.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Simular incidente" }));
    expect(inc.launch).toHaveBeenCalledOnce();
  });

  it("warns that the current session is left when its hour differs, and locks the choices while busy", () => {
    const inc = incident({ catalog, selected: "polonia-2025", busy: true });
    render(<IncidentPanel inc={inc} sessionPoint="nov2026-1300" />);
    expect(screen.getByText("y se sale de la actual", { exact: false })).toBeTruthy();
    expect((screen.getByRole("button", { name: "Simulando…" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "A · Reactiva" }) as HTMLButtonElement).disabled).toBe(true);
    const radio = screen.getAllByRole("radio")[0];
    expect(radio.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(radio);
    expect(inc.select).not.toHaveBeenCalled();
  });

  it("changes the policy of the defensive agents", () => {
    const inc = incident({ catalog });
    render(<IncidentPanel inc={inc} sessionPoint={null} />);
    expect(screen.getByRole("button", { name: "C · Adaptativa" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "A · Reactiva" }));
    expect(inc.setPolicy).toHaveBeenCalledWith("A");
  });
});

describe("IncidentPanel: the result", () => {
  it("shows the consequence card, the response, prevention, sources and both notices, and hides the catalog", () => {
    render(<IncidentPanel inc={incident({ catalog, result })} sessionPoint="nov2026-1300" />);
    const heading = screen.getByRole("heading", { name: "Huatacondo" });
    expect(document.activeElement).toBe(heading); // the finished run takes the focus to its heading
    expect(screen.getByRole("status").textContent).toBe("Simulación terminada: Huatacondo");
    expect(screen.getByText("Resumen del incidente.")).toBeTruthy();
    expect(screen.getByText("Apagón regional")).toBeTruthy();
    expect(screen.getByText("Consecuencia")).toBeTruthy();
    expect(screen.getByText("personas sin suministro")).toBeTruthy();
    expect(screen.queryByText(/semilla/)).toBeNull();
    expect(screen.getByText("continuidad de misión")).toBeTruthy();
    expect(screen.getByText("Segmentar la red")).toBeTruthy();
    expect(screen.getByText("Nota del informe")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Fuente informe" }).getAttribute("href")).toBe("https://example.org/aar");
    // the policy of the run, not the one selected now (C)
    expect(screen.getByText("Incidente simulado · política A · Reactiva", { exact: false })).toBeTruthy();
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.getAllByText(NOTICES[0], { exact: false }).length).toBe(2); // top and bottom
  });

  it("offers to play the cascade only for cycles that have one, and to stop the one playing from the result card", () => {
    const inc = incident({ catalog, result });
    const { rerender } = render(<IncidentPanel inc={inc} sessionPoint={null} />);
    expect(screen.getAllByRole("button", { name: "Ver cascada en el mapa" }).length).toBe(2); // result card and cycle 2
    fireEvent.click(screen.getAllByRole("button", { name: "Ver cascada en el mapa" })[1]);
    expect(inc.play).toHaveBeenCalledWith(2);
    rerender(<IncidentPanel inc={{ ...inc, playing: 2 }} sessionPoint={null} />);
    expect(screen.getByText("El mapa muestra la cascada del ciclo 2.")).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Quitar del mapa" })[0]);
    expect(inc.stop).toHaveBeenCalledOnce();
  });

  it("writes area names and EDAC names in the cycles and folds the cycles without effects", () => {
    render(<IncidentPanel inc={incident({ catalog, result })} sessionPoint={null} />);
    expect(screen.getByText("Se pierde generación en Arica–Iquique")).toBeTruthy();
    expect(screen.getByText("Ver los 2 ciclos")).toBeTruthy();
    expect(screen.getByText("Rearmar la defensa EDAC Centro-Sur")).toBeTruthy();
  });

  it("titles an absorbed incident and its measures as such, with no big zero figures", () => {
    const quiet = { ...result, level: "L0", cascades: [], card: { ...result.card, consequence_level: "L0", people_without_power: 0, load_shed_mw: 0 } };
    render(<IncidentPanel inc={incident({ catalog, result: quiet })} sessionPoint={null} />);
    expect(screen.getByRole("heading", { name: "El sistema absorbió el efecto" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Qué lo haría más robusto" })).toBeTruthy();
    expect(screen.queryByText("personas sin suministro")).toBeNull();
  });

  it("says when no cycle had a cascade, and closes the incident", () => {
    const inc = incident({ catalog, result: { ...result, cascades: [] } });
    render(<IncidentPanel inc={inc} sessionPoint={null} />);
    expect(screen.getByText("Ningún ciclo tuvo una cascada en la red: el sistema absorbió el efecto.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Ver cascada en el mapa" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Cerrar incidente" }));
    expect(inc.close).toHaveBeenCalledOnce();
  });
});
