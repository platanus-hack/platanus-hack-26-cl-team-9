import { describe, expect, it } from "vitest";
import { actionText, decisionText, notice, render, NOTICE } from "./text";

const nar = {
  notice: NOTICE,
  actions: { field_verification: "Enviar una cuadrilla a verificar {target}" },
  decisions: { vetoed: "Vetada" },
  rationale: { log_crew_too_far: "Logística no envía cuadrilla: ninguna libre llegaría a tiempo." },
  verdicts: { area_segmented: "El área está aislada" },
};

describe("narration", () => {
  it("fills the backend templates", () => {
    expect(actionText(nar, "field_verification", "A09")).toBe("Enviar una cuadrilla a verificar A09");
    expect(decisionText(nar, "vetoed:log_crew_too_far")).toBe("Vetada: Logística no envía cuadrilla: ninguna libre llegaría a tiempo.");
    expect(render("ISR ({confidence})", { confidence: 0.8 })).toBe("ISR (80%)");
  });

  it("always has the hypothetical-scenario notice", () => {
    expect(notice(null)).toBe(NOTICE);
    expect(notice(nar)).toContain("se modela el efecto, no el ataque");
  });
});
