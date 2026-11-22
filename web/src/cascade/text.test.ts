import { describe, expect, it } from "vitest";
import { clock, conditionDate, conditionName, cutName, narrate, shutdownNode, substationLines } from "./text";
import type { Event, Network } from "./types";

describe("operating condition labels", () => {
  it("takes the name from the label's parenthetical", () => {
    expect(conditionName("Noviembre 2026, 13:00 (mediodía solar)")).toBe("Mediodía solar");
    expect(conditionName("Noviembre 2026, 20:00 (punta nocturna)")).toBe("Punta nocturna");
    expect(conditionName("Febrero 2025, 03:00 (demanda mínima)")).toBe("Demanda mínima");
    expect(conditionName("Febrero 2025, 15:00 (referencia del 25F)")).toBe("Referencia 25F");
  });

  it("falls back to the whole label", () => {
    expect(conditionName("Marzo 2027, 10:00")).toBe("Marzo 2027, 10:00");
    expect(conditionName("Marzo 2027 ()")).toBe("Marzo 2027 ()");
  });

  it("writes the date line from the snapshot", () => {
    expect(conditionDate("2026-11-01 13:00")).toBe("1 nov 2026 · 13:00");
    expect(conditionDate("2025-02-01 03:00")).toBe("1 feb 2025 · 03:00");
    expect(conditionDate(undefined)).toBe("");
  });
});

describe("clock", () => {
  it("adds the simulated seconds to the snapshot time", () => {
    expect(clock("2025-02-01 15:00", 61.25)).toEqual({ hms: "15:01:01", tenths: "15:01:01,2" });
    expect(clock(undefined, 0).tenths).toBe("--:--:--,-");
  });
});

const NET: Network = {
  nodes: [
    { id: "B000", name: "S/E CERRO NAVIA", lon: 0, lat: 0, kv: 220, zone: "centro_sur", map_nodes: [] },
    { id: "B001", name: "S/E POLPAICO", lon: 0, lat: 0, kv: 500, zone: "centro_sur", map_nodes: [] },
    { id: "B002", name: "S/E ALTO JAHUEL", lon: 0, lat: 0, kv: 500, zone: "centro_sur", map_nodes: [] },
  ],
  lines: [
    { id: "R000", a: "B000", b: "B001", kv: 220, capacity_mw: 100, x_pu: 0.1, map_edges: [], branches: [] },
    { id: "R001", a: "B001", b: "B002", kv: 500, capacity_mw: 100, x_pu: 0.1, map_edges: [], branches: [] },
    { id: "R002", a: "B002", b: "B000", kv: 220, capacity_mw: 100, x_pu: 0.1, map_edges: [], branches: [] },
  ],
};
const cutEvent = (ids: string[]): Event => ({ t: 0, type: "line_cut", ids, text_key: "line_cut", params: {} });

describe("substation shutdown", () => {
  it("lists the lines with one end at the substation", () => {
    expect(substationLines(NET, "B001")).toEqual(["R000", "R001"]);
    expect(substationLines(NET, "B999")).toEqual([]);
  });

  it("names a substation scenario and a line scenario", () => {
    expect(shutdownNode("sub-B001")).toBe("B001");
    expect(shutdownNode("R001")).toBeNull();
    expect(cutName(NET, "sub-B001")).toBe("Subestación Polpaico");
    expect(cutName(NET, "R000")).toBe("Cerro Navia – Polpaico (220 kV)");
  });

  it("narrates one or several lines opening at t = 0", () => {
    expect(narrate(cutEvent(["R000"]), NET)).toBe("Sale de servicio la línea Cerro Navia – Polpaico (220 kV).");
    expect(narrate(cutEvent(["R000", "R001"]), NET)).toBe("Salen de servicio las líneas Cerro Navia – Polpaico (220 kV) y Polpaico – Alto Jahuel (500 kV).");
    expect(narrate(cutEvent(["R000", "R001", "R002"]), NET)).toBe(
      "Salen de servicio las líneas Cerro Navia – Polpaico (220 kV), Polpaico – Alto Jahuel (500 kV) y Alto Jahuel – Cerro Navia (220 kV).",
    );
  });
});
