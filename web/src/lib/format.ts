/** Whole number with Chilean separators. */
export const fmt = (n: number) => Math.round(n).toLocaleString("es-CL");

export function formatNumber(value: number | null | undefined, digits = 0): string {
  return value == null ? "s/d" : value.toLocaleString("es-CL", { maximumFractionDigits: digits });
}

export function formatPeople(n: number): string {
  return n >= 1e6 ? `${(n / 1e6).toLocaleString("es-CL", { maximumFractionDigits: 1 })} millones` : n.toLocaleString("es-CL");
}
