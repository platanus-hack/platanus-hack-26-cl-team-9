import { useMemo, useState, type FormEvent } from "react";
import { countryName, ISO3_CODES } from "../map/iso3";
import type { RegionalGrid } from "../map/regional";
import { cleanText, MAX_BYTES, parseUpload, type UploadOk } from "../map/upload";
import { mb } from "./text";

type FieldErrors = { file: string[]; country: string[] };
const NO_ERRORS: FieldErrors = { file: [], country: [] };

/** The messages of one field, right under it; a list when the file failed several checks. */
function FieldError({ id, lead, messages }: { id: string; lead?: string; messages: string[] }) {
  if (!messages.length) return null;
  if (messages.length === 1) return <p className="field-error" id={id} role="alert">{messages[0]}</p>;
  return (
    <div className="field-error" id={id} role="alert">
      {lead && <p>{lead}</p>}
      <ul>{messages.map((m, i) => <li key={i}>{m}</li>)}</ul>
    </div>
  );
}

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
  // Each error sits next to the field it belongs to (B3-09): the file's checks under Archivo, the country under País.
  const [errors, setErrors] = useState<FieldErrors>(NO_ERRORS);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<{ result: UploadOk; name: string } | null>(null);
  const options = useMemo(() => ISO3_CODES.map((code) => ({ code, label: `${countryName(code)} (${code})` })).sort((a, b) => a.label.localeCompare(b.label, "es")), []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setPending(null);
    const missing: FieldErrors = { file: file ? [] : ["Elige un archivo."], country: country ? [] : ["Indica el país al que pertenece la red."] };
    if (!file || !country) return setErrors(missing);
    if (file.size > MAX_BYTES) return setErrors({ ...NO_ERRORS, file: [`El archivo pesa ${mb(file.size)} MB; el máximo es ${MAX_BYTES / 1024 / 1024} MB.`] });
    setBusy(true);
    try {
      const result = parseUpload(await file.text(), file.size, country);
      if (!result.ok) return setErrors({ ...NO_ERRORS, file: result.errors });
      setErrors(NO_ERRORS);
      const label = cleanText(name) || result.name || cleanText(file.name.replace(/\.(geo)?json$/i, "")) || "Red subida";
      if (result.fileCountry && result.fileCountry !== country) setPending({ result, name: label });
      else add({ name: label, country, grid: result.grid });
    } catch {
      setErrors({ ...NO_ERRORS, file: ["No se pudo leer el archivo."] });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card data-form upload-form" onSubmit={submit} noValidate>
      <p className="meta">
        Un archivo GeoJSON con subestaciones, líneas (cada una dice qué dos subestaciones une) y centrales, o un archivo de red en
        formato JSON con barras y líneas. Hasta 10 MB, 5.000 subestaciones y 10.000 líneas. Se guarda solo en este navegador y se
        muestra sin simulación.
      </p>
      <label><span>Archivo</span>
        <input type="file" accept=".json,.geojson,application/json,application/geo+json" aria-invalid={errors.file.length > 0 || undefined} aria-describedby={errors.file.length ? "upload-file-error" : undefined}
          onChange={(e) => { setFile(e.target.files?.[0] ?? null); setErrors((x) => ({ ...x, file: [] })); setPending(null); }} />
      </label>
      <FieldError id="upload-file-error" lead="No se aceptó el archivo:" messages={errors.file} />
      <label><span>País (obligatorio)</span>
        <select value={country} required aria-invalid={errors.country.length > 0 || undefined} aria-describedby={errors.country.length ? "upload-country-error" : undefined}
          onChange={(e) => { setCountry(e.target.value); setErrors((x) => ({ ...x, country: [] })); setPending(null); }}>
          <option value="">Elige un país</option>
          {options.map((o) => <option key={o.code} value={o.code}>{o.label}</option>)}
        </select>
      </label>
      <FieldError id="upload-country-error" messages={errors.country} />
      <label><span>Nombre (opcional)</span>
        <input value={name} maxLength={80} placeholder="Nombre del archivo" onChange={(e) => setName(e.target.value)} />
      </label>
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
