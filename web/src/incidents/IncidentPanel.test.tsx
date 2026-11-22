// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Timeline } from "../cascade/types";
import { NOTICES, type IncidentInfo } from "./incidents";
import { IncidentPanel } from "./IncidentPanel";
import type { Incident, IncidentResult } from "./useIncident";

afterEach(cleanup);

const info = (over: Partial<IncidentInfo> = {}): IncidentInfo => ({
  id: "huatacondo-2026", title: "Huatacondo", date: "2026-08-26", kind: "cyber_documented", verified: true,
  sources: [{ label: "Fuente uno", url: "https://example.org/uno" }], notes: ["Nota del catálogo"], mitigations: [],
  operating_point: "nov2026-1300", horizon: 24, effects: [{ cycle: 2, type: "C1_generation_loss", target: "A01", params: { mw: 88.1 } }], ...over,
});
const catalog = { notices: [], cost_basis: {}, incidents: [info(), info({ id: "polonia-2025", title: "Polonia", kind: "reference_not_cyber", operating_point: "feb2025-1500" })] };

function incident(over: Partial<Incident> = {}): Incident {
  return {
    catalog: null, selected: null, policy: "C", busy: false, error: null, result: null, playing: null,
    load: vi.fn(), select: vi.fn(), setPolicy: vi.fn(), launch: vi.fn(async () => {}), play: vi.fn(), stop: vi.fn(), close: vi.fn(), cascadeAt: () => null, ...over,
  };
}
const result: IncidentResult = {
  sid: "s1", runId: "r1", seed: 7, incident: info(), level: "L2", minutesPerCycle: 5,
  card: {
    incident: "huatacondo-2026", consequence_level: "L2", people_without_power: 3_512_405, load_shed_mw: 2028.5, unserved_energy_mwh: 8114.1,
    failure_cost_usd: 17_834_910, cost_per_hour_usd: 17_834_910, outage_duration_h: { value: 1, is_assumption: true }, cost_breakdown: {}, cost_basis: {},
    note: "Nota de la tarjeta.", notices: [],
  },
  indicators: { mission_continuity: 0.8, situational_awareness: { time_to_understanding_cycles: 2, understood: true } },
  aar: { title: "Huatacondo", summary: "Resumen del incidente.", effect: "", prevention: ["Segmentar la red"], notes: ["Nota del informe"], sources: [{ label: "Fuente informe", url: "https://example.org/aar" }], verified: true, notices: [] },
  timeline: [{ cycle: 1, t_min: 5, lines: ["Sin novedades"] }, { cycle: 2, t_min: 10, lines: ["Se pierde generación"] }],
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

  it("shows the error instead of the loading text when the catalog fails", () => {
    render(<IncidentPanel inc={incident({ error: "No se pudo conectar con el backend (x)." })} sessionPoint={null} />);
    expect(screen.getByText("No se pudo conectar con el backend (x).")).toBeTruthy();
    expect(screen.queryByText("Cargando el catálogo…")).toBeNull();
  });

  it("lists the incidents in file order with their tag and effects, and selects one", () => {
    const inc = incident({ catalog });
    render(<IncidentPanel inc={inc} sessionPoint={null} />);
    const radios = screen.getAllByRole("radio");
    expect(radios.map((r) => r.querySelector(".inc-title")?.textContent)).toEqual(["Huatacondo", "Polonia"]);
    expect(screen.getByText("referencia, no es ciber")).toBeTruthy();
    expect(screen.getAllByText("Ciclo 2: Pérdida de generación en área A01 (88 MW)").length).toBe(2);
    fireEvent.click(radios[1]);
    expect(inc.select).toHaveBeenCalledWith("polonia-2025");
  });

  it("keeps the launch button off until an incident is chosen, then launches", () => {
    const { unmount } = render(<IncidentPanel inc={incident({ catalog })} sessionPoint={null} />);
    expect((screen.getByRole("button", { name: "Simular incidente" }) as HTMLButtonElement).disabled).toBe(true);
    unmount();
    const inc = incident({ catalog, selected: "huatacondo-2026" });
    render(<IncidentPanel inc={inc} sessionPoint="nov2026-1300" />);
    expect(screen.getByText("Corre en la sesión actual.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Simular incidente" }));
    expect(inc.launch).toHaveBeenCalledOnce();
  });

  it("warns that the current session is left when its hour differs, and disables the button while busy", () => {
    render(<IncidentPanel inc={incident({ catalog, selected: "polonia-2025", busy: true })} sessionPoint="nov2026-1300" />);
    expect(screen.getByText("y se saldrá de la actual", { exact: false })).toBeTruthy();
    expect((screen.getByRole("button", { name: "Simulando…" }) as HTMLButtonElement).disabled).toBe(true);
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
    expect(screen.getByRole("heading", { name: "Huatacondo" })).toBeTruthy();
    expect(screen.getByText("Resumen del incidente.")).toBeTruthy();
    expect(screen.getByText("L2 · apagón regional")).toBeTruthy();
    expect(screen.getByText("personas sin luz")).toBeTruthy();
    expect(screen.getByText("continuidad de misión")).toBeTruthy();
    expect(screen.getByText("Segmentar la red")).toBeTruthy();
    expect(screen.getByText("Nota del informe")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Fuente informe" }).getAttribute("href")).toBe("https://example.org/aar");
    expect(screen.getByText("Incidente simulado · política C", { exact: false })).toBeTruthy();
    expect(screen.queryByRole("radiogroup")).toBeNull();
    expect(screen.getAllByText(NOTICES[0], { exact: false }).length).toBe(2); // top and bottom
  });

  it("offers to play the cascade only for cycles that have one, and to stop the one playing", () => {
    const inc = incident({ catalog, result });
    const { rerender } = render(<IncidentPanel inc={inc} sessionPoint={null} />);
    expect(screen.getAllByRole("button", { name: "Ver cascada en el mapa" }).length).toBe(1);
    fireEvent.click(screen.getByRole("button", { name: "Ver cascada en el mapa" }));
    expect(inc.play).toHaveBeenCalledWith(2);
    rerender(<IncidentPanel inc={{ ...inc, playing: 2 }} sessionPoint={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Quitar del mapa" }));
    expect(inc.stop).toHaveBeenCalledOnce();
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
