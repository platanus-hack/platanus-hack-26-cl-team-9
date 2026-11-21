import { CITIES } from "./cities";
import { markerLabel, type Impact, type Marker } from "./simulation";
import { formatPeople, int, narrate, secs, shortTitle } from "./text";
import type { MarkerState } from "./Timeline";
import type { Network } from "./types";

export interface LocatedMarker { marker: Marker; lon: number; lat: number; zone: string }

/**
 * HTML layer over the map: event pins, the current event's callout and, on the offline map, city names. Each anchor
 * carries data-lon/data-lat; the app's animation loop moves it to the projected point every frame.
 */
export function MapOverlays(p: { markers: LocatedMarker[]; states: Map<Marker, MarkerState>; visible: number; network: Network; impact: Impact; showCities: boolean; select(t: number): void }) {
  const first = p.markers[0];
  return (
    <>
      {p.showCities && CITIES.map((c) => (
        <div key={c.name} className={`anchor city ${c.side}`} data-lon={c.lon} data-lat={c.lat}><span className="city-dot" /><span className="city-name">{c.name}</span></div>
      ))}
      {p.markers.map((lm) => {
        const state = p.states.get(lm.marker) ?? "future";
        if (state === "future") return null;
        const m = lm.marker;
        const last = m.events[m.events.length - 1];
        // A group can reach past the current second: the callout shows its latest event that has already happened.
        const nowNumber = Math.min(m.last, p.visible);
        const now = m.events[nowNumber - m.first];
        const title = shortTitle(narrate(m.events[0], p.network));
        return (
          <div key={m.first} className={`anchor map-event ${state}`} data-lon={lm.lon} data-lat={lm.lat}>
            <button className={`pin ${state}${m.first !== m.last ? " group" : ""}`} onClick={() => p.select(last.t)} aria-label={`Evento ${markerLabel(m)}: ${title}`}>{markerLabel(m)}</button>
            {state === "current" && (
              <div className="callout">
                <div className="callout-head"><span className="fault">{secs(now.t)} s · evento {nowNumber}</span><span>{lm.zone}</span></div>
                <h4>{shortTitle(narrate(now, p.network))}</h4>
                <div className="callout-figures">
                  <div><b className="cream">{formatPeople(p.impact.people)}</b><span>personas sin suministro</span></div>
                  <div><b>{int(p.impact.lostLoadMw)} MW</b><span>carga perdida</span></div>
                </div>
              </div>
            )}
            {state === "past" && lm === first && (
              <div className="pin-label"><b>{title}</b><span>{secs(m.events[0].t)}{m.first !== m.last ? `–${secs(last.t)}` : ""} s</span></div>
            )}
          </div>
        );
      })}
    </>
  );
}
