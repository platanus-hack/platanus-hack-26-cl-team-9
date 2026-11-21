import { KV_COLORS, LOW_KV_COLOR, TECH_COLORS, type Rgb } from "./map/layers";

const TECH_LABELS: Record<string, string> = {
  solar: "Solar",
  eolica: "Eólica",
  hidro: "Hidroeléctrica",
  termica: "Térmica",
  bioenergia: "Bioenergía",
  geotermica: "Geotérmica",
};

/** Why: every colour and height on the map must be readable without asking the team. */
export function Legend() {
  return (
    <div className="legend">
      <h2>Cómo leer el mapa</h2>

      <h3>Líneas de transmisión</h3>
      <p>Planas sobre el mapa. El color indica la tensión. Las de 500 kV son las más gruesas.</p>
      {_kvRows()}

      <h3>Subestaciones</h3>
      <p>Prismas pequeños de seis lados. Mismo color que las líneas, según su tensión. La altura también crece con la tensión.</p>

      <h3>Generación</h3>
      <p>Columnas redondas más anchas. Una por subestación, con la suma de los MW de las centrales conectadas a ella. La altura es proporcional a los MW. El color es la tecnología con más MW en ese nodo.</p>
      {Object.entries(TECH_COLORS).map(([tech, rgb]) => _row(TECH_LABELS[tech] ?? tech, rgb))}

      <h3>Escala</h3>
      <p>Las alturas están exageradas para verse a escala país: unos 120 m por MW y 30 m por kV. No representan nada físico.</p>

      <h3>Datos</h3>
      <p>
        Red unificada del repo (<code>data/processed/geo/</code>): IDE Energía, API del CEN, PyPSA-CL e INE Censo 2024.
        Se muestran las 1.078 subestaciones de la red principal y 1.245 centrales. Contorno: BCN, simplificado.
      </p>

      <h3>Navegación</h3>
      <p>Arrastrar para mover. Rueda para zoom. Ctrl o clic derecho más arrastrar para inclinar y girar. Pasar el ratón muestra nombre, kV o MW.</p>
    </div>
  );
}

function _kvRows() {
  return [
    ...KV_COLORS.map(([kv, rgb], i) => _row(i === 0 ? `${kv} kV` : `${kv} a ${KV_COLORS[i - 1][0] - 1} kV`, rgb)),
    _row(`Menos de ${KV_COLORS[KV_COLORS.length - 1][0]} kV o sin dato`, LOW_KV_COLOR),
  ];
}

function _row(label: string, [r, g, b]: Rgb) {
  return (
    <div className="legend-row" key={label}>
      <span className="swatch" style={{ background: `rgb(${r}, ${g}, ${b})` }} />
      {label}
    </div>
  );
}
