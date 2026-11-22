import type { ViewMode } from "../map/baseMap";
import { DEMAND_COLOR, FAULT, MIN_FLOW_MW, MW_TO_METERS, NODE_COLOR } from "./layers";
import { assumptionTitle, plainAssumption } from "./text";
import type { BusState, Index, Network } from "./types";
import { TECH_COLORS, TECH_NAMES } from "../map/layers";
import type { RegionalGrid } from "../map/regional";

const css = (c: number[]) => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${(c[3] ?? 255) / 255})`;

/** Words a first-time reader meets in the panel and the map, explained once (F-13). */
const GLOSSARY: [string, string][] = [
  ["Isla", "Parte de la red que queda separada del resto y tiene que equilibrar sola su generación y su demanda."],
  ["Corte automático de carga (EDAC)", "Esquema que desconecta demanda por escalones cuando la frecuencia cae, para salvar el resto de la isla."],
  ["N-1", "Criterio de seguridad: la red debería seguir operando si falla un solo elemento, por ejemplo una línea."],
  ["MW", "Megawatt: mide la potencia que se genera o se consume en un instante."],
  ["Frecuencia", "Ritmo al que gira la red: 50 Hz en Chile. Cae cuando falta generación; bajo 47,5 Hz el modelo apaga la isla."],
];

/**
 * "Ayuda" view: four steps to use the map, what the map draws that the legend card does not say, and a short glossary.
 * Line colours live in the map legend only, so this view does not repeat them (E-26, F-13).
 */
export function HelpPanel({ network, buses, mode, regional }: { network: Network; buses: Record<string, BusState>; mode: ViewMode; regional?: RegionalGrid | null }) {
  const columns = network.nodes.filter((n) => (buses[n.id]?.load_mw ?? 0) > 20).length;
  return (
    <div className="prose">
      <p>Sub50 simula qué pasa en la red eléctrica de Chile cuando se corta una línea o se apaga una subestación. La red está resumida: {network.nodes.length} subestaciones y {network.lines.length} líneas.</p>
      <h3>Cómo se usa</h3>
      <ol className="steps">
        <li>Elige una línea o subestación en el mapa.</li>
        <li>Pulsa Sacar de servicio: la cascada se reproduce sola.</li>
        <li>Lee en Simulación quién queda sin suministro.</li>
        <li>Prueba otra hora en Condiciones o repón con Prender todo.</li>
      </ol>
      <p className="meta">También puedes buscarla por nombre en Simulación. Un segundo clic sobre la elegida también la saca de servicio; un doble clic rápido no corta nada. La barra espaciadora reproduce o pausa. En Desastres hay apagones reales listos para ver.</p>
      <h3>En el mapa</h3>
      <p>El color de las líneas sigue a la pestaña: en Red indica la tensión y en Simulación cuánto de su capacidad usa cada línea. La tarjeta de la esquina inferior derecha dice qué significa cada color.</p>
      <Row swatch={<span className="dot" />} label={`Puntos blancos que se mueven: el sentido del flujo, en líneas con ${MIN_FLOW_MW} MW o más.`} />
      <Row swatch={<span className="dot big" style={{ background: NODE_COLOR }} />} label="Subestación con suministro (más grande: 500 kV)." />
      <Row swatch={<span className="dot big" style={{ background: FAULT }} />} label="Subestación sin suministro: su isla se apagó." />
      <Row swatch={mode === "3d" ? <span className="col" style={{ background: DEMAND_COLOR }} /> : <span className="dot big" style={{ background: DEMAND_COLOR, opacity: 0.5 }} />}
        label={mode === "3d"
          ? `Demanda de la subestación (${MW_TO_METERS} m por MW, exagerada); ${columns} subestaciones tienen más de 20 MW. Se activa en el botón de capas.`
          : `Demanda de la subestación: el círculo crece con los MW; ${columns} subestaciones tienen más de 20 MW. Se activa en el botón de capas.`} />
      <p>Cada evento de la cascada tiene un número, el mismo en el historial, la línea de tiempo y el mapa. El evento actual es rojo.</p>
      {regional && <RegionalLegend regional={regional} />}
      <h3>Glosario</h3>
      <dl className="glossary">
        {GLOSSARY.map(([term, text]) => <div key={term}><dt>{term}</dt><dd>{text}</dd></div>)}
      </dl>
      <p className="meta">No se dibujan la generación por central, los transformadores, la tensión ni las redes bajo 66 kV.</p>
    </div>
  );
}

/** Where the data comes from, linked when `docs/datasets.md` (section 7) records the address. Never an invented link. */
const SOURCES: { what: string; name: string; url?: string }[] = [
  { what: "Red de transmisión, subestaciones y centrales", name: "IDE Energía, Ministerio de Energía", url: "https://ide-energia.minenergia.cl/server/rest/services/IDE_Energia/Visor_IDE_Energ%C3%ADa/MapServer" },
  { what: "Tramos y subestaciones oficiales", name: "Infotécnica, Coordinador Eléctrico Nacional", url: "https://api-infotecnica.coordinador.cl/v1/tramos/" },
  { what: "Despacho y demanda de cada hora, simulados", name: "PyPSA-CL", url: "https://github.com/paredes-vergara/PyPSA-CL" },
  { what: "Población por comuna", name: "INE, Censo 2024", url: "https://censo2024.ine.gob.cl/resultados/" },
  { what: "Escalones de corte de carga y secuencia del 25F", name: "Informe del Coordinador Eléctrico Nacional sobre el 25F", url: "https://www.coordinador.cl/wp-content/uploads/2025/03/2025-03-19-RESUMEN-EJECUTIVO.pdf" },
  { what: "Costo de la energía no servida", name: "Costo de falla de la CNE", url: "https://www.cne.cl/wp-content/uploads/2026/03/Res.-Ext.-N112-comunica-CFCD-y-CFLD.pdf" },
  { what: "Cascada, frecuencia y personas sin suministro", name: "motor Sub50, calculado por este proyecto" },
];

/**
 * "Fuentes y supuestos" view: three plain lines, the sources as a list of links, then each engine assumption as a row
 * that opens (F-29, B-05). The base map line names Mapbox or the outline in use.
 */
export function SourcesPanel({ assumptions, index, basemap }: { assumptions: string[]; index: Index | null; basemap: { name: string; url?: string } }) {
  return (
    <div className="prose">
      <ul className="plain-lines">
        <li>Sub50 usa una red de Chile resumida, hecha con datos públicos.</li>
        <li>La generación y la demanda de cada hora son simuladas, no medidas.</li>
        <li>Las cifras son estimaciones del modelo, no una predicción. El ícono (i) junto a cada número dice de dónde sale.</li>
      </ul>
      <h3>Fuentes</h3>
      <ul className="source-list">
        {[...SOURCES, { what: "Mapa base", ...basemap }].map((s) => (
          <li key={s.what}><span className="meta">{s.what}</span>{s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer">{s.name}</a> : <span>{s.name}</span>}</li>
        ))}
      </ul>
      <h3>Supuestos del motor · {assumptions.length}</h3>
      <div className="assumption-list">
        {assumptions.map((raw) => {
          const text = plainAssumption(raw);
          const title = assumptionTitle(text);
          if (title === text) return <p className="assumption" key={raw}>{text}</p>;
          return (
            <details className="assumption" key={raw}>
              <summary>{title}</summary>
              <p>{text}</p>
            </details>
          );
        })}
      </div>
      {index && <p className="meta">Horas simuladas: {index.points.map((p) => p.label).join("; ")}.</p>}
    </div>
  );
}

function Row({ swatch, label }: { swatch: React.ReactNode; label: string }) {
  return <div className="legend-row"><span className="legend-swatch">{swatch}</span><span>{label}</span></div>;
}

/** The other countries are drawn from public sources with their own licences; the help says what and from where. */
function RegionalLegend({ regional }: { regional: RegionalGrid }) {
  const sources = new Map(regional.countries.flatMap((c) => c.sources.map((s) => [s.id, s] as const)));
  const techs = [...new Set(regional.plants.map((p) => p.tech ?? ""))].filter((t) => TECH_COLORS[t]);
  return (
    <>
      <h3>Otras redes de Latinoamérica</h3>
      <p>Solo se dibujan, no se simulan, con los mismos colores de tensión y grosores que la red de Chile. Están resumidas igual: una barra por subestación y las líneas en paralelo fundidas en una, rectas entre dos subestaciones, desde 66 kV. Los discos son la generación de cada subestación, con el color de su tecnología.</p>
      {regional.countries.map((c) => <Row key={c.country} swatch={<span className="dot big" style={{ background: NODE_COLOR }} />} label={`${c.name}: ${c.counts.lines} líneas y ${c.counts.substations} subestaciones (de ${c.raw_counts.lines} y ${c.raw_counts.substations} en la fuente); ${c.plant_count} centrales en ${c.counts.plants} puntos.`} />)}
      {techs.map((tech) => <Row key={tech} swatch={<span className="dot big" style={{ background: css(TECH_COLORS[tech]) }} />} label={TECH_NAMES[tech] ?? tech} />)}
      <p className="meta">Fuentes: {[...sources.values()].map((s) => `${s.attribution} (${s.license})`).join("; ")}.</p>
    </>
  );
}
