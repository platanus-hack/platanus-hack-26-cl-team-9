// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Edits } from "./edits";
import type { OutageCost, Prepared, SimulationResult } from "./gridsApi";
import { NetworkState } from "./NetworkState";
import type { BusState, Network, Timeline } from "./types";

const network: Network = {
  nodes: [
    { id: "B1", name: "S/E CERRO NAVIA", lon: 0, lat: 0, kv: 220, zone: "centro_sur", map_nodes: [] },
    { id: "B2", name: "S/E POLPAICO", lon: 0, lat: 0, kv: 220, zone: "centro_sur", map_nodes: [] },
  ],
  lines: [{ id: "L1", a: "B1", b: "B2", kv: 220, capacity_mw: 400, x_pu: 0.01, map_edges: [], branches: ["R1"] }],
};
const buses: Record<string, BusState> = { B1: { gen_mw: 0, load_mw: 100, people: 800 }, B2: { gen_mw: 200, load_mw: 0, people: 200 } };
const timeline = {
  scenario: "x", label: "x", failed_elements: ["L1"], truncated: false, duration_s: 10,
  events: [
    { t: 1.5, type: "line_overload_open", ids: ["L1"], text_key: "", params: {} },
    { t: 4, type: "island_blackout", ids: ["B2"], text_key: "", params: { buses: 1, load_mw: 100, reason: "frequency" } },
  ],
  frames: [{ t: 10, edges: {}, dark: ["B1"], islands: [] }], frequency_hz: {},
  summary: { people_without_power: 800, load_shed_mw: 100, load_total_mw: 400, stages: 1, lines_opened: ["L1"], dark_buses: 1, islands: [] }, assumptions: [],
} as unknown as Timeline;
const cost: OutageCost = {
  energy_not_served_mwh: 734, cost_usd: 2_500_000, cost_per_hour_usd: 340_000,
  breakdown: { dark_mw: 100, shed_mw: 0, dark_share: 1, total_blackout_factor: 1 },
  outage_hours: { value: 7.34 }, unserved_cost_usd_per_mwh: { value: 6000 }, assumptions: ["supuesto uno"],
};
const none: Edits = { lines: [], buses: [] };

function setup(over: Partial<Parameters<typeof NetworkState>[0]> = {}) {
  const fns = { restoreLine: vi.fn(), restoreBus: vi.fn(), restoreAll: vi.fn(), dropChange: vi.fn() };
  const props = { network, buses, point: "nov2026-1300", edits: none, result: null, timeline: null, prepared: null, ...fns, ...over };
  render(<NetworkState {...props} />);
  return fns;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(cost), { status: 200 })));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("NetworkState", () => {
  it("says there are no changes and does not call the cost endpoint", () => {
    setup();
    expect(screen.getByRole("heading", { name: "Sin cambios" })).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("lists the cut lines and the shut-down substations and puts each one back alone", () => {
    const a = setup({ edits: { lines: ["L1"], buses: ["B2"] } });
    expect(screen.getByRole("heading", { name: "Cambios en la red · 2" })).toBeTruthy();
    const rows = screen.getAllByRole("button", { name: "Reponer" });
    fireEvent.click(rows[0]);
    expect(a.restoreLine).toHaveBeenCalledWith("L1");
    fireEvent.click(rows[1]);
    expect(a.restoreBus).toHaveBeenCalledWith("B2");
    fireEvent.click(screen.getByRole("button", { name: "Reponer todo" }));
    expect(a.restoreAll).toHaveBeenCalledOnce();
  });

  it("marks a line that leaves with its substation", () => {
    const result = { dropped_lines: ["L1"], warnings: [{ code: "w", message: "Aviso del motor" }], direct: { load_mw: 100, gen_mw: 0, people: 800 } } as unknown as SimulationResult;
    setup({ edits: { lines: ["L1"], buses: ["B1"] }, result });
    expect(screen.getByText("sale con su subestación", { exact: false })).toBeTruthy();
    expect(screen.getByText("Aviso del motor")).toBeTruthy();
    expect(screen.getByText("Apagar esa subestación deja sin suministro a 800 personas", { exact: false })).toBeTruthy();
  });

  it("describes a prepared change, how many elements it matched, and drops it", () => {
    const prepared = {
      changes: [{ target: "demand", matched: 3 }], totals: { people_total: 1000, load_total_mw: 400, gen_total_mw: 500 }, overloaded_lines: [{ id: "L1", kv: 220, loading_pct: 130 }],
    } as unknown as Prepared;
    const a = setup({ edits: { lines: [], buses: [], changes: [{ target: "demand", factor: 2, zones: ["NG"] }] }, prepared });
    expect(screen.getByText("Demanda × 2 · zona NG · 3 elementos")).toBeTruthy();
    expect(screen.getByText("1 líneas sobre su límite")).toBeTruthy();
    expect(screen.getByText("La red está preparada", { exact: false })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Quitar" }));
    expect(a.dropChange).toHaveBeenCalledWith(0);
  });

  it("shows the cascade outcome with the cost from the server and the lines the engine opened", async () => {
    setup({ edits: { lines: ["L1"], buses: [] }, timeline });
    expect(screen.getByRole("heading", { name: "Al final de la caída" })).toBeTruthy();
    expect(screen.getByText("800")).toBeTruthy(); // people without power, same figure as the Simulación tab
    expect(screen.getByText("Calculando el costo…")).toBeTruthy();
    await waitFor(() => expect(screen.getByText("costo de la caída")).toBeTruthy());
    expect(screen.getByText("apagón total · 7,34 h", { exact: false })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Consecuencias en la red · 2" })).toBeTruthy();
    expect(screen.getByText("1,5 s")).toBeTruthy();
    expect(screen.getByText("1 subestaciones, 100 MW · frecuencia bajo 47,5 Hz")).toBeTruthy();
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/v1/grids/cost");
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({ point: "nov2026-1300", open_lines: ["L1"], out_buses: [] });
  });

  it("takes the cost from the timeline summary when it has one, without asking the backend", () => {
    const withCost = { ...timeline, summary: { ...timeline.summary, failure_cost_usd: 984_336_303, unserved_energy_mwh: 81_442.7, outage_duration_h: { value: 7.34, is_assumption: false } } } as Timeline;
    setup({ edits: { lines: ["L1"], buses: [] }, timeline: withCost });
    expect(screen.getByText("US$ 984,3 M")).toBeTruthy();
    expect(screen.getByText("apagón parcial · 7,34 h calibradas")).toBeTruthy();
    expect(screen.queryByText("Calculando el costo…")).toBeNull();
    expect(vi.mocked(fetch)).not.toHaveBeenCalled();
  });

  it("says the cost is pending when the backend has no endpoint, and shows the error when it fails", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    setup({ edits: { lines: ["L1"], buses: [] }, timeline });
    await waitFor(() => expect(screen.getByText("Costo de la caída: el servidor aún no lo calcula.")).toBeTruthy());
    cleanup();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 500 })));
    setup({ edits: { lines: ["L1"], buses: [] }, timeline });
    await waitFor(() => expect(screen.getByText("No se pudo calcular el costo.")).toBeTruthy());
  });
});
