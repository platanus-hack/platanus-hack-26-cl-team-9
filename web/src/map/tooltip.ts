/** Tooltip of the grid layers: a generation column or a substation. Shared by the offline and Mapbox maps. */
export function gridTooltip({ object, layer }: { object?: any; layer?: { id: string } | null }): string | null {
  if (!object || !layer) return null;
  if (layer.id === "generation") return `${object.name}\n${Math.round(object.mw)} MW · ${object.tech}`;
  return `${object.name}\n${object.kv ?? "?"} kV`;
}
