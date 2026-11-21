import { COLUMN_COLOR, LOADING_BANDS, NO_FLOW_COLOR, OPEN_COLOR, SELECTED_COLOR, WIDTH_BY_KV, MIN_FLOW_MW, MW_TO_METERS } from "./layers";
import type { BusState, Network } from "./types";

const css = (c: number[]) => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${(c[3] ?? 255) / 255})`;

/** Why: every colour, size and moving element of mapa 3 is explained next to the map, with the counts of what is drawn. */
export function CascadeLegend({ network, buses }: { network: Network; buses: Record<string, BusState> }) {
  const columns = network.nodes.filter((n) => (buses[n.id]?.load_mw ?? 0) > 20).length;
  return (
    <section className="legend">
      <h2>Qué muestra el mapa</h2>
      <p className="muted">
        Red reducida del SEN: {network.nodes.length} subestaciones y {network.lines.length} líneas. Cada línea une dos subestaciones en línea recta
        y agrupa los circuitos en paralelo y los transformadores.
      </p>

      <h3>Líneas de transmisión</h3>
      <p>El color indica cuánto de su capacidad usa la línea en la etapa que estás viendo.</p>
      {LOADING_BANDS.map((b) => <Row key={b.label} swatch={<Bar color={css(b.color)} />} label={b.label} />)}
      <Row swatch={<Bar color={css(OPEN_COLOR)} height={2} />} label="Línea abierta (cortada o disparada por sobrecarga)" />
      <Row swatch={<Bar color={css(SELECTED_COLOR)} />} label="Línea que cortaste" />
      <Row swatch={<Bar color={css(NO_FLOW_COLOR)} />} label="Sin flujo calculado" />
      <p className="sub">Grosor según la tensión</p>
      {WIDTH_BY_KV.map((w) => <Row key={w.label} swatch={<Bar color="#cbd5e1" height={w.width} />} label={w.label} />)}

      <h3>Flujo de potencia</h3>
      <Row swatch={<span className="dot" />} label={`Puntos blancos que se mueven por la línea, en el sentido del flujo. Solo líneas con ${MIN_FLOW_MW} MW o más.`} />

      <h3>Subestaciones</h3>
      <Row swatch={<span className="dot big" style={{ background: "#e2e8f0" }} />} label="Con energía (más grande: 500 kV)" />
      <Row swatch={<span className="dot big" style={{ background: "#ef4444", border: "1px solid #000" }} />} label="Sin energía: su isla se apagó" />

      <h3>Demanda</h3>
      <Row swatch={<span className="col" style={{ background: css(COLUMN_COLOR) }} />} label={`Barra rectangular azul: demanda de la subestación (${MW_TO_METERS} m por MW, exagerada). ${columns} subestaciones con más de 20 MW. Desaparece al apagarse.`} />

      <h3>Lo que no se dibuja</h3>
      <p className="muted">Generación por central, transformadores, tensión y potencia reactiva, y las redes bajo 66 kV. Las líneas del mapa 1 y 2 (1.930) se agrupan aquí en {network.lines.length}.</p>
    </section>
  );
}

function Row({ swatch, label }: { swatch: React.ReactNode; label: string }) {
  return <div className="legend-row"><span className="legend-swatch">{swatch}</span><span>{label}</span></div>;
}

function Bar({ color, height = 5 }: { color: string; height?: number }) {
  return <span className="bar" style={{ background: color, height }} />;
}
