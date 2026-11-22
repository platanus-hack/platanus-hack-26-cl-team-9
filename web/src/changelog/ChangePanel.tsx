import type { Entry } from "./changelog";
import "./changelog.css";

/** Historial de cambios: blue entries are changes made to the network, red ones are things that went down. */
/** A click on an entry with elements shows them on the map (`locate`). */
export function ChangePanel({ entries, locate }: { entries: Entry[]; locate(ids: string[]): void }) {
  return (
    <div className="changelog">
      <p className="chg-legend"><span className="chg-tag ajuste">Ajuste</span> se modificó la red <span className="chg-tag caida">Caída</span> algo dejó de funcionar</p>
      {entries.length === 0 ? <p className="note">Aún no hay cambios. Corta una línea, ajusta un valor o simula una cascada.</p> : (
        <ol className="chg-list">
          {entries.map((e, i) => (
            <li key={i} className={`chg-item ${e.kind}${e.ids.length ? " pick" : ""}`} {...(e.ids.length ? {
              role: "button", tabIndex: 0, title: "Ver en el mapa", onClick: () => locate(e.ids),
              onKeyDown: (k: React.KeyboardEvent) => { if (k.key === "Enter" || k.key === " ") { k.preventDefault(); locate(e.ids); } },
            } : {})}>
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
