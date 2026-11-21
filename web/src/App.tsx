import { useEffect, useRef } from "react";
import { Legend } from "./Legend";
import { mountChileMapWorkflow } from "./map/chileMap";

// Full-screen map with a floating panel on the right (styles.css).
export function App() {
  const mapRef = useRef<HTMLDivElement>(null);

  useEffect(() => mountChileMapWorkflow(mapRef.current!), []);

  return (
    <div className="layout">
      <div className="map" ref={mapRef} />
      <div className="panels">
        <h1>CascadaSEN</h1>
        <p className="muted">Red eléctrica nacional (SEN). Paneles de simulación pendientes: contador, cadena de eventos, frecuencia y validación.</p>
        <Legend />
      </div>
    </div>
  );
}
