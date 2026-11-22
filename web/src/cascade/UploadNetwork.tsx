import { useMemo, useState, type FormEvent } from "react";
import { countryName, ISO3_CODES } from "../map/iso3";
import type { RegionalGrid } from "../map/regional";
import { cleanText, MAX_BYTES, parseUpload, type UploadOk } from "../map/upload";

export interface UploadedNetwork { name: string; country: string; grid: RegionalGrid }

/**
 * "Subir una red" (issue #49 part C): a file and its country (required). The file is checked by `parseUpload` (size,
 * format, country, coordinates, line ends, numbers) and refused with the list of what failed. When the file names
 * another country, the user confirms which one to use. Nothing leaves the browser.
 */
export function UploadNetwork({ add, cancel }: { add(n: UploadedNetwork): void; cancel(): void }) {
  const [file, setFile] = useState<File | null>(null);
  const [country, setCountry] = useState("");
  const [name, setName] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{ result: UploadOk; name: string } | null>(null);
  const options = useMemo(() => ISO3_CODES.map((code) => ({ code, label: `${countryName(code)} (${code})` })).sort((a, b) => a.label.localeCompare(b.label, "es")), []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setPending(null);
    if (!file) return setErrors(["Elige un archivo."]);
    if (!country) return setErrors(["Indica el país al que pertenece la red."]);
    if (file.size > MAX_BYTES) return setErrors([`El archivo pesa ${(file.size / 1024 / 1024).toFixed(1)} MB; el máximo es ${MAX_BYTES / 1024 / 1024} MB.`]);
    setBusy(true);
    try {
      const result = parseUpload(await file.text(), file.size, country);
      if (!result.ok) return setErrors(result.errors);
      setErrors([]);
      const label = cleanText(name) || result.name || cleanText(file.name.replace(/\.(geo)?json$/i, "")) || "Red subida";
      if (result.fileCountry && result.fileCountry !== country) setPending({ result, name: label });
      else add({ name: label, country, grid: result.grid });
    } catch {
      setErrors(["No se pudo leer el archivo."]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card data-form upload-form" onSubmit={submit} noValidate>
      <p className="meta">
        Un archivo GeoJSON con el esquema regional (subestaciones, líneas con extremos <code>a</code> y <code>b</code>, centrales) o el JSON de red v1
        de <code>docs/network-format.md</code>. Hasta 10 MB, 5.000 subestaciones y 10.000 líneas. Se guarda solo en este navegador y se muestra
        sin simulación.
      </p>
      <label><span>Archivo</span>
        <input type="file" accept=".json,.geojson,application/json,application/geo+json" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setErrors([]); setPending(null); }} />
      </label>
      <label><span>País (obligatorio)</span>
        <select value={country} required onChange={(e) => { setCountry(e.target.value); setPending(null); }}>
          <option value="">Elige un país</option>
          {options.map((o) => <option key={o.code} value={o.code}>{o.label}</option>)}
        </select>
      </label>
      <label><span>Nombre (opcional)</span>
        <input value={name} maxLength={80} placeholder="Nombre del archivo" onChange={(e) => setName(e.target.value)} />
      </label>
      {errors.length > 0 && (
        <div className="note" role="alert">
          <p>No se aceptó la red:</p>
          <ul>{errors.map((m, i) => <li key={i}>{m}</li>)}</ul>
        </div>
      )}
      {pending && (
        <div className="notice" role="alert">
          <span>El archivo dice que la red es de {countryName(pending.result.fileCountry!)} ({pending.result.fileCountry}); indicaste {countryName(country)} ({country}). Se escribirá {country} en cada elemento.</span>
          <span className="row-btns">
            <button type="button" className="secondary-btn" onClick={() => add({ name: pending.name, country, grid: pending.result.grid })}>Usar {country}</button>
            <button type="button" className="text-btn" onClick={() => setPending(null)}>Cancelar</button>
          </span>
        </div>
      )}
      <div className="row-btns">
        <button type="submit" className="primary-btn" disabled={busy}>{busy ? "Revisando…" : "Subir red"}</button>
        <button type="button" className="text-btn" onClick={cancel}>Cancelar</button>
      </div>
    </form>
  );
}
