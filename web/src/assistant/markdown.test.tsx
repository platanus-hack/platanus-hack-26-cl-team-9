import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { blocks, inline, Markdown } from "./markdown";

describe("assistant markdown", () => {
  it("splits a reply into paragraphs, lists and headings", () => {
    const text = "He agregado el datacenter.\n\n**Efectos:**\n- Nuevas sobrecargas: R063\n- Corte de carga: 0 MW\n\n1. Uno\n2. Dos\n### Nota";
    expect(blocks(text)).toEqual([
      { kind: "p", lines: ["He agregado el datacenter."] },
      { kind: "p", lines: ["**Efectos:**"] },
      { kind: "ul", items: ["Nuevas sobrecargas: R063", "Corte de carga: 0 MW"] },
      { kind: "ol", items: ["Uno", "Dos"] },
      { kind: "h", text: "Nota" },
    ]);
  });

  it("renders bold and code and never turns text into HTML", () => {
    const html = renderToStaticMarkup(<Markdown text={"**Datacenter** en `B010`\n- <img src=x onerror=alert(1)>"} />);
    expect(html).toContain("<b>Datacenter</b> en <code>B010</code>");
    expect(html).toContain("&lt;img src=x onerror=alert(1)&gt;");
    expect(html).not.toContain("<img");
  });

  it("leaves unpaired markers as written", () => {
    expect(inline("2 * 3 = 6 y **sin cerrar")).toEqual(["2 * 3 = 6 y **sin cerrar"]);
  });
});
