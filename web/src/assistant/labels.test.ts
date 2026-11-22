import { describe, expect, it } from "vitest";
import { argsText, errorMessage, refreshFor, resultText, toolName, truncatedText } from "./labels";

describe("labels", () => {
  it("names tools in Spanish and falls back to the raw name", () => {
    expect(toolName("add_datacenter")).toBe("Agregar datacenter");
    expect(toolName("cut_lines")).toBe("Cortar líneas");
    expect(toolName("step")).toBe("Avanzar ciclos");
    expect(toolName("new_tool")).toBe("new_tool");
  });

  it("writes arguments as one readable line", () => {
    expect(argsText("add_datacenter", { bus: "Antofagasta", mw: 120 })).toBe("Antofagasta · 120 MW");
    expect(argsText("cut_lines", { lines: ["R014", "R015"] })).toBe("R014, R015");
    expect(argsText("repair_lines", {})).toBe("todas las líneas abiertas");
    expect(argsText("step", { cycles: 3 })).toBe("3 ciclos de 5 min");
    expect(argsText("add_line", { a: "B001", b: "B002", kv: 220, capacity_mw: 300 })).toBe("B001 – B002 · 220 kV · 300 MW");
    expect(argsText("edit_element", { element_id: "D001", changes: { mw: 80 } })).toBe("D001 · mw = 80");
    expect(argsText("list_options", null)).toBe("");
  });

  it("summarises results from the fields the tool returned", () => {
    expect(resultText("add_datacenter", true, { id: "D001", warnings: [] })).toBe("id D001");
    expect(resultText("add_datacenter", true, { id: "D001", bus_name: "S/E ESCONDIDA" })).toBe("id D001 · en S/E ESCONDIDA");
    expect(resultText("cut_lines", true, { open_lines: ["R014"], load_shed_mw: 120.5, dark_buses: 3 })).toBe("líneas abiertas: R014 · 120,5 MW sin servir · 3 barras sin suministro");
    expect(resultText("step", true, { run: { cycle: 3 }, cycles: [{}, {}, {}] })).toBe("3 ciclos simulados · ciclo 3");
    expect(resultText("cut_lines", false, { error: "Línea desconocida" })).toBe("Línea desconocida");
    expect(resultText("cut_lines", false, null)).toBe("La herramienta falló.");
  });

  it("maps each tool to what the map reloads", () => {
    expect(refreshFor("add_datacenter")).toBe("network");
    expect(refreshFor("reset_network")).toBe("network");
    expect(refreshFor("cut_lines")).toBe("state");
    expect(refreshFor("repair_lines")).toBe("state");
    expect(refreshFor("step")).toBe("snapshots");
    expect(refreshFor("describe_network")).toBeNull();
  });

  it("explains errors by status", () => {
    expect(errorMessage(429, 12)).toBe("Demasiados mensajes; espera 12 s.");
    expect(errorMessage(503)).toBe("El asistente no está habilitado en este servidor.");
    expect(errorMessage(422)).toBe(errorMessage(413));
    expect(errorMessage(500)).toBe("El asistente falló; reintenta.");
    expect(truncatedText("deadline")).toContain("tiempo máximo");
    expect(truncatedText(null)).toBeNull();
  });
});

describe("prepare_scenario in the chat", () => {
  it("names the tool in Spanish and reads its changes instead of [object Object]", () => {
    expect(toolName("prepare_scenario")).toBe("Preparar el mapa");
    const args = {
      changes: [
        { target: "demand", places: ["Antofagasta"], add: 120 },
        { target: "generation", places: ["Iquique"], tech: ["solar"], add: 80 },
        { target: "generation", tech: ["hidro"], factor: 0.5 },
      ],
      open_lines: ["R239"],
    };
    expect(argsText("prepare_scenario", args)).toBe("+120 MW demanda en Antofagasta · +80 MW solar en Iquique · × 0,5 hidro · líneas fuera: R239");
  });

  it("reads a new substation as its megawatts and place", () => {
    const args = { changes: [{ target: "substation", places: ["Vallenar"], name: "S/E Solar", generator_mw: 120, tech: ["solar"] }] };
    expect(argsText("prepare_scenario", args)).toBe("+120 MW solar en Vallenar");
  });

  it("says where each place went and when a change touched nothing", () => {
    const result = {
      prepared: { changes: [{ matched: 1, places: [{ bus_name: "S/E ANTOFAGASTA" }] }, { matched: 0 }] },
      simulation: { with_changes: { people_without_power: 1200 } },
    };
    expect(resultText("prepare_scenario", true, result)).toBe("en S/E ANTOFAGASTA · 1 cambio no tocó ninguna subestación · 1.200 personas sin suministro");
    expect(resultText("prepare_scenario", true, {})).toBe("mapa preparado");
  });
});

describe("find_line in the chat", () => {
  it("names the tool and shows the line it found", () => {
    expect(toolName("find_line")).toBe("Buscar línea");
    const one = { lines: [{ id: "R239", name: "S/E NUEVA MAITENCILLO – S/E NUEVA PAN DE AZUCAR (500 kV)" }] };
    expect(resultText("find_line", true, one)).toBe("R239 · S/E NUEVA MAITENCILLO – S/E NUEVA PAN DE AZUCAR (500 kV)");
    const many = { lines: ["R006", "R026", "R027", "R028", "R029"].map((id) => ({ id, name: id })) };
    expect(resultText("find_line", true, many)).toBe("5 líneas: R006, R026, R027, R028…");
  });
});
