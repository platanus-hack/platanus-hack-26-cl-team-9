/** Whole number with Chilean separators. */
export const fmt = (n: number) => Math.round(n).toLocaleString("es-CL");

export function formatNumber(value: number | null | undefined, digits = 0): string {
  return value == null ? "s/d" : value.toLocaleString("es-CL", { maximumFractionDigits: digits });
}
