export async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`No se pudo cargar ${url}: ${response.status}`);
  return response.json() as Promise<T>;
}
