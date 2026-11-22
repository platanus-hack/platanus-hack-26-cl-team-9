import type { Entry } from "./changelog";
import "./changelog.css";

/** Historial de cambios: blue entries are changes made to the network, red ones are things that went down. */
export function ChangePanel({ entries }: { entries: Entry[] }) {
  return (
    <div className="changelog">
      <p className="chg-legend"><span className="chg-tag ajuste">Ajuste</span> se modificó la red <span className="chg-tag caida">Caída</span> algo dejó de funcionar</p>
      {entries.length === 0 ? <p className="note">Aún no hay cambios. Corta una línea, ajusta un valor o simula una cascada.</p> : (
        <ol className="chg-list">
          {entries.map((e, i) => (
            <li key={i} className={`chg-item ${e.kind}`}>
              <span className={`chg-tag ${e.kind}`}>{e.kind === "ajuste" ? "Ajuste" : "Caída"}</span>
              <span className="chg-text">{e.text}</span>
              {e.when && <span className="chg-when">{e.when}</span>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
