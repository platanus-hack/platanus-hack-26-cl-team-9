// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Pick } from "./clicks";
import type { Edits } from "./edits";
import type { Prepared, Supply } from "./gridsApi";
import { SelectionCard } from "./SelectionCard";
import type { BusState, Frame, Network } from "./types";

afterEach(cleanup);

const network: Network = {
  nodes: [
    { id: "B1", name: "S/E CERRO NAVIA", lon: -70.7, lat: -33.4, kv: 220, zone: "centro_sur", map_nodes: [] },
    { id: "B2", name: "S/E POLPAICO", lon: -70.9, lat: -33.1, kv: 220, zone: "centro_sur", map_nodes: [] },
  ],
  lines: [{ id: "L1", a: "B1", b: "B2", kv: 220, capacity_mw: 400, x_pu: 0.01, map_edges: [], branches: ["R1", "R2"] }],
};
const buses: Record<string, BusState> = {
  B1: { gen_mw: 0, load_mw: 120, people: 2_500_000 },
  B2: { gen_mw: 300, load_mw: 10, people: 1000 },
};
const frame: Frame = { t: 5, edges: { L1: { flow_mw: 450, status: "overload", loading: 1.125 } }, dark: [], islands: [] };
const noEdits: Edits = { lines: [], buses: [] };

function setup(over: Partial<Parameters<typeof SelectionCard>[0]> = {}) {
  const fns = { select: vi.fn(), clear: vi.fn(), cutLine: vi.fn(), restore: vi.fn(), shutdown: vi.fn(), powerOn: vi.fn(), setFactor: vi.fn() };
  const selection: Pick = { kind: "line", id: "L1" };
  const props = { network, buses, frame, selection, cut: null, year: 2026, shutDown: false, edits: null, prepared: null, supply: null, ...fns, ...over };
  const view = render(<SelectionCard {...props} />);
  return { ...fns, ...view };
}

describe("SelectionCard: a line", () => {
  it("shows the capacity, the flow, the loading and the overloaded status", () => {
    setup();
    expect(screen.getByRole("heading", { name: "Cerro Navia – Polpaico (220 kV)" })).toBeTruthy();
    expect(screen.getByText("2 circuitos del modelo fundidos en uno", { exact: false })).toBeTruthy();
    expect(screen.getByText("113 %")).toBeTruthy(); // loading 1.125
    expect(screen.getByText("sobrecargada")).toBeTruthy();
    expect(screen.getByText("Flujo de Cerro Navia a Polpaico.")).toBeTruthy();
  });

  it("cuts the line, and offers to reconnect it when it is the cut of the scenario", () => {
    const a = setup();
    fireEvent.click(screen.getByRole("button", { name: "Sacar de servicio" }));
    expect(a.cutLine).toHaveBeenCalledWith("L1");
    cleanup();
    const b = setup({ cut: "L1" });
    expect(screen.queryByRole("button", { name: "Sacar de servicio" })).toBeNull();
    expect(screen.getByText("(corte de este escenario)", { exact: false })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Volver a conectar" }));
    expect(b.restore).toHaveBeenCalledOnce();
  });

  it("closes the card and selects an end substation", () => {
    const a = setup({ frame: { ...frame, dark: ["B2"] } });
    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(a.clear).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: /Polpaico · sin suministro/ }));
    expect(a.select).toHaveBeenCalledWith({ kind: "node", id: "B2" });
  });

  it("puts the action before the factor fields, which wait closed under Modificar valores (E-22)", () => {
    const { container } = setup({ edits: { lines: [], buses: [] } });
    const details = container.querySelector("details.edit-block") as HTMLDetailsElement;
    expect(details.open).toBe(false);
    expect(details.querySelector("summary")?.textContent).toContain("Modificar valores");
    const action = screen.getByRole("button", { name: "Sacar de servicio" });
    expect(action.compareDocumentPosition(details) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("renders nothing when the selected line is not in the network", () => {
    const { container } = setup({ selection: { kind: "line", id: "ZZ" } });
    expect(container.innerHTML).toBe("");
  });

  it("applies the typed capacity factor on blur and restores the field when it is out of range", () => {
    const a = setup({ edits: noEdits });
    const input = screen.getByLabelText("Factor de capacidad") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "1.5" } });
    fireEvent.blur(input);
    expect(a.setFactor).toHaveBeenCalledWith("lines", "L1", 1.5);
    fireEvent.change(input, { target: { value: "9" } }); // the backend's bound is 5
    fireEvent.blur(input);
    expect(a.setFactor).toHaveBeenCalledTimes(1);
    expect(input.value).toBe("1");
  });

  it("hides the edit block where components cannot be edited", () => {
    setup({ edits: null });
    expect(screen.queryByText("Modificar valores")).toBeNull();
  });
});

describe("SelectionCard: a substation", () => {
  const node = (over: Partial<Parameters<typeof SelectionCard>[0]> = {}) => setup({ selection: { kind: "node", id: "B1" }, ...over });

  it("shows generation, demand, people and the connected lines with their loading", () => {
    node();
    expect(screen.getByRole("heading", { name: "Cerro Navia" })).toBeTruthy();
    expect(screen.getByText("2,5 M")).toBeTruthy();
    expect(screen.getByText("Líneas conectadas · 1")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Cerro Navia – Polpaico \(220 kV\)113 %/ })).toBeTruthy();
  });

  it("selects a connected line from the list", () => {
    const a = node();
    fireEvent.click(screen.getByRole("button", { name: /Cerro Navia – Polpaico/ }));
    expect(a.select).toHaveBeenCalledWith({ kind: "line", id: "L1" });
  });

  it("shuts the substation down and powers it on again", () => {
    const a = node();
    fireEvent.click(screen.getByRole("button", { name: "Apagar subestación" }));
    expect(a.shutdown).toHaveBeenCalledWith("B1");
    cleanup();
    const b = node({ shutDown: true });
    expect(screen.getByText("Centro-sur · apagada", { exact: false })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Volver a encender" }));
    expect(b.powerOn).toHaveBeenCalledWith("B1");
  });

  it("sets the population factor of this substation", () => {
    const a = node({ edits: noEdits });
    const input = screen.getByLabelText("Factor de personas");
    fireEvent.change(input, { target: { value: "2" } });
    fireEvent.keyDown(input, { key: "Enter" });
    fireEvent.blur(input);
    expect(a.setFactor).toHaveBeenCalledWith("population", "B1", 2);
  });

  it("shows the prepared values only for the touched figures, and the supply row of a generator", () => {
    const prepared = {
      changes: [{ target: "population", matched: 1, elements: [{ id: "B1", load_mw: [120, 150], people: 3_000_000 }] }],
    } as unknown as Prepared;
    const supply: Supply = { sources: [{ id: "B2", name: "Polpaico", zone: "centro_sur", gen_mw: [300, 300], should_feed: 1_000_000, feeds: 400_000, pct_fed: 40 }], by_zone: {} };
    node({ prepared });
    expect(screen.getByText("demanda preparada")).toBeTruthy();
    expect(screen.getByText("150", { exact: false })).toBeTruthy();
    expect(screen.getByText("3 M")).toBeTruthy();
    expect(screen.getAllByText("=").length).toBe(1); // generation was not touched
    cleanup();
    setup({ selection: { kind: "node", id: "B2" }, supply });
    expect(screen.getByText("40,00 %", { exact: false })).toBeTruthy();
  });
});
