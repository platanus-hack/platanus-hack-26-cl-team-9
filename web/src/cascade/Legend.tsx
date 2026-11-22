import type { ViewMode } from "../map/baseMap";
import { DEAD_LINE, DEMAND_COLOR, FAULT, LOAD_BANDS, MIN_FLOW_MW, MW_TO_METERS, NODE_COLOR, OPEN_LINE, VOLTAGE_TIERS } from "./layers";
import type { BusState, Index, Network } from "./types";
import { TECH_COLORS } from "../map/layers";
import type { RegionalGrid } from "../map/regional";

const css = (c: number[]) => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${(c[3] ?? 255) / 255})`;

/** "Ayuda" view: every colour, size and moving element of the map, with the counts of what is drawn. */
export function HelpPanel({ network, buses, mode, regional }: { network: Network; buses: Record<string, BusState>; mode: ViewMode; regional?: RegionalGrid | null }) {
  const columns = network.nodes.filter((n) => (buses[n.id]?.load_mw ?? 0) > 20).length;
  return (
    <div className="prose">
      <p>Red reducida del Sistema Eléctrico Nacional: {network.nodes.length} subestaciones y {network.lines.length} líneas. Cada línea une dos subestaciones en línea recta y agrupa los circuitos en paralelo y los transformadores.</p>
      <h3>Cómo se usa</h3>
      <p>Haz clic en una línea o una subestación para ver su detalle arriba del panel; clic en el mapa vacío o Escape lo cierra. Un segundo clic en la línea seleccionada, o el botón Sacar de servicio de su detalle, la saca de servicio (un doble clic rápido no corta nada): el motor calcula la cascada y la línea de tiempo la reproduce (barra espaciadora: reproducir o pausar). Volver a conectar vuelve al caso base. En una sesión compartida, el segundo clic en una subestación seleccionada la apaga (abre todas sus líneas) y Volver a encender la repone. La condición de operación (fecha y hora) se elige bajo cada escenario, en Escenarios, y el corte se mantiene, para comparar el mismo corte a otra hora.</p>
      <h3>Color de las líneas</h3>
      <p>En Red el color indica la tensión: tonos fríos, más claros a mayor tensión. En Simulación indica qué parte de su capacidad usa la línea en ese segundo, de verde a naranja. El rojo siempre es falla. El grosor siempre indica la tensión.</p>
      {VOLTAGE_TIERS.map((t) => <Row key={t.label} swatch={<Bar color={t.color} height={t.width + 1} />} label={t.label} />)}
      {LOAD_BANDS.map((b) => <Row key={b.label} swatch={<Bar color={b.color} />} label={`${b.label} de su capacidad${b.upTo === Infinity ? " (sobrecarga, más gruesa)" : ""}`} />)}
      <Row swatch={<Bar color={DEAD_LINE} outline />} label="Sin tensión: sus dos extremos quedaron sin suministro" />
      <Row swatch={<Bar color={OPEN_LINE} dashed />} label="Fuera de servicio: cortada o abierta por sobrecarga (sobre 120 %)" />
      <h3>Flujo de potencia</h3>
      <Row swatch={<span className="dot" />} label={`Puntos blancos que se mueven en el sentido del flujo, solo en líneas con ${MIN_FLOW_MW} MW o más. Se apagan en el botón de capas.`} />
      <h3>Subestaciones</h3>
      <Row swatch={<span className="dot big" style={{ background: NODE_COLOR }} />} label="Con suministro (más grande: 500 kV)" />
      <Row swatch={<span className="dot big" style={{ background: FAULT }} />} label="Sin suministro: su isla se apagó" />
      <h3>Demanda</h3>
      <Row swatch={mode === "3d" ? <span className="col" style={{ background: DEMAND_COLOR }} /> : <span className="dot big" style={{ background: DEMAND_COLOR, opacity: 0.5 }} />}
        label={mode === "3d"
          ? `Columna: demanda de la subestación (${MW_TO_METERS} m por MW, exagerada). ${columns} subestaciones con más de 20 MW. Se activa en el botón de capas.`
          : `Círculo: demanda de la subestación, su área crece con los MW. ${columns} subestaciones con más de 20 MW. Se activa en el botón de capas.`} />
      <h3>Eventos</h3>
      <p>Cada evento tiene un número, el mismo en el historial, la línea de tiempo y el mapa. El evento actual es rojo; los eventos a pocas décimas de segundo comparten un marcador (1·2).</p>
      {regional && <RegionalLegend regional={regional} />}
      <h3>Lo que no se dibuja</h3>
      <p className="meta">Generación por central, transformadores, tensión y potencia reactiva, y las redes bajo 66 kV.</p>
    </div>
  );
}

/** "Fuentes y supuestos" view: where the data comes from and every assumption of the engine. */
export function SourcesPanel({ assumptions, index }: { assumptions: string[]; index: Index | null }) {
  return (
    <div className="prose">
      <h3>Fuentes</h3>
      <ul>
        <li>Red de transmisión, subestaciones y centrales: IDE Energía (Ministerio de Energía), en data/processed/geo.</li>
        <li>Puntos de operación (despacho y demanda por hora): modelo PyPSA-CL, simulado, no medido.</li>
        <li>Cascada, frecuencia y personas sin suministro: motor Sub50 (docs/engine.md), precalculado en la caché de la app.</li>
        <li>Mapa base: Mapbox cuando hay token; si no, el contorno de Chile de data/processed/chile.geojson.</li>
      </ul>
      <h3>Supuestos · {assumptions.length}</h3>
      <ol>{assumptions.map((a) => <li key={a}>{a}</li>)}</ol>
      {index && <p className="meta">Puntos de operación disponibles: {index.points.map((p) => p.label).join("; ")}.</p>}
    </div>
  );
}

function Row({ swatch, label }: { swatch: React.ReactNode; label: string }) {
  return <div className="legend-row"><span className="legend-swatch">{swatch}</span><span>{label}</span></div>;
}

function Bar({ color, height = 3, outline = false, dashed = false }: { color: string; height?: number; outline?: boolean; dashed?: boolean }) {
  if (dashed) return <svg width="26" height="4" viewBox="0 0 26 4" aria-hidden><path d="M0 2H26" stroke={color} strokeWidth="2" strokeDasharray="3 2.5" /></svg>;
  return <span className="bar" style={{ background: color, height, outline: outline ? "1px solid #FFFFFF40" : undefined }} />;
}

/** The other countries are drawn from public sources with their own licences; the help says what and from where. */
function RegionalLegend({ regional }: { regional: RegionalGrid }) {
  const sources = new Map(regional.countries.flatMap((c) => c.sources.map((s) => [s.id, s] as const)));
  return (
    <>
      <h3>Otras redes de Latinoamérica</h3>
      <p>Red de contexto: solo se dibuja, no se simula. Usa los mismos colores, grosores y subestaciones que la de Chile; en Simulación sus líneas quedan en gris porque no tienen flujo calculado. Reducida como la de Chile: una barra por subestación, las líneas en paralelo se funden en una y se dibujan rectas entre dos subestaciones. Desde 66 kV; los puntos grandes son la generación de cada subestación (color por tecnología).</p>
      {regional.countries.map((c) => <Row key={c.country} swatch={<span className="dot big" style={{ background: NODE_COLOR }} />} label={`${c.name}: ${c.counts.lines} líneas y ${c.counts.substations} subestaciones (de ${c.raw_counts.lines} y ${c.raw_counts.substations} en la fuente); ${c.plant_count} centrales en ${c.counts.plants} puntos`} />)}
      {Object.entries(TECH_COLORS).map(([tech, c]) => <Row key={tech} swatch={<span className="dot big" style={{ background: css([c[0], c[1], c[2], 160]) }} />} label={tech} />)}
      <p className="meta">Fuentes: {[...sources.values()].map((s) => `${s.attribution} (${s.license})`).join("; ")}.</p>
    </>
  );
}
