import { describe, expect, it } from "vitest";
import { CAPACITY_MW, ELEMENT_MW, fieldError, formErrors, LAT, loadingText, mwText, parseNumber, type Spec } from "./forms";

describe("Datos forms", () => {
  const mw: Spec = { key: "mw", label: "MW", type: "number", required: true, ...ELEMENT_MW };
  const lat: Spec = { key: "lat", label: "Latitud", type: "number", ...LAT };

  it("parses numbers with a decimal comma or dot and nothing else", () => {
    expect(parseNumber("2,5")).toBe(2.5);
    expect(parseNumber(" 120 ")).toBe(120);
    expect(parseNumber("-33.45")).toBe(-33.45);
    expect(parseNumber("12abc")).toBeNaN();
    expect(parseNumber("")).toBeNaN();
  });

  it("explains each refused value in Spanish before anything is sent", () => {
    expect(fieldError(mw, "")).toBe("Obligatorio.");
    expect(fieldError(mw, "mucho")).toBe("Escribe un número (por ejemplo 2,5).");
    expect(fieldError(mw, "-5")).toBe("Debe ser más de 0 y hasta 3.000.");
    expect(fieldError(mw, "0")).toBe("Debe ser más de 0 y hasta 3.000.");
    expect(fieldError(mw, "2,5")).toBeNull();
    expect(fieldError(lat, "")).toBeNull(); // optional
    expect(fieldError(lat, "-10")).toBe("Debe ser entre -56 y -17.");
    expect(fieldError({ key: "capacity_mw", label: "Capacidad", type: "number", ...CAPACITY_MW }, "6000")).toBe("Debe ser más de 0 y hasta 5.000.");
    expect(fieldError({ key: "a", label: "Barra A", required: true, bus: true }, "barra 1")).toBe("Escribe el id de una barra, como B010.");
    expect(fieldError({ key: "a", label: "Barra A", required: true, bus: true }, "B010")).toBeNull();
    expect(fieldError({ key: "name", label: "Nombre", maxLength: 3 }, "abcd")).toBe("Máximo 3 caracteres.");
  });

  it("collects the errors of a whole form by field", () => {
    expect(formErrors([mw, lat], { mw: "", lat: "-33" })).toEqual({ mw: "Obligatorio." });
    expect(formErrors([mw, lat], { mw: "10", lat: "-33" })).toEqual({});
  });

  it("keeps decimals of small MW values and shows loading with one decimal", () => {
    expect(mwText(2.5)).toBe("2,5");
    expect(mwText(2.1)).toBe("2,1");
    expect(mwText(120)).toBe("120");
    expect(mwText(1234.6)).toBe("1.235");
    expect(loadingText(1.004)).toBe("100,4 %");
    expect(loadingText(0.5)).toBe("50,0 %");
  });
});
