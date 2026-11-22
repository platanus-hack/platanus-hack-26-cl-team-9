/**
 * Spanish texts of the assistant chat: tool names, readable arguments, short result summaries and error messages.
 * Tool names are the MCP ones (backend/src/cascadasen/mcp/tools.py `OPERATIONS`, docs/assistant.md). Summaries only
 * repeat what the tool returned (docs/cyber.md section 8); the full result stays in the card's detail.
 */

const TOOL_NAMES: Record<string, string> = {
  start_session: "Abrir sesión",
  join_session: "Unirse a la sesión",
  end_session: "Cerrar sesión",
  list_options: "Ver opciones",
  describe_network: "Describir la red",
  add_datacenter: "Agregar datacenter",
  add_generator: "Agregar generador",
  add_line: "Agregar línea",
  add_bus: "Agregar barra",
  add_substation: "Agregar subestación",
  edit_element: "Editar elemento",
  remove_element: "Quitar elemento",
  reset_network: "Restablecer la red",
  cut_lines: "Cortar líneas",
  repair_lines: "Reparar líneas",
  get_grid_state: "Leer el estado de la red",
  start_run: "Iniciar corrida",
  inject_event: "Inyectar evento",
  step: "Avanzar ciclos",
  submit_action: "Enviar acción defensiva",
  run_status: "Estado de la corrida",
  run_report: "Informe de la corrida",
  after_action: "Revisión posterior",
  replay: "Repetir la corrida",
  list_incident_scenarios: "Ver incidentes documentados",
  start_incident_run: "Iniciar un incidente",
  prepare_scenario: "Preparar el mapa",
  find_line: "Buscar línea",
};
const TARGETS: Record<string, string> = { demand: "demanda", generation: "generación", population: "personas", lines: "capacidad de líneas", substation: "subestación nueva" };
const TECHS: Record<string, string> = {
  eolica: "eólica", bateria: "batería", termica: "térmica", carbon: "carbón", diesel: "diésel", bioenergia: "bioenergía", geotermica: "geotérmica",
};

export const toolName = (name: string) => TOOL_NAMES[name] ?? name;

type Json = Record<string, unknown>;
const isObj = (v: unknown): v is Json => !!v && typeof v === "object" && !Array.isArray(v);
const num = (v: unknown) => (typeof v === "number" ? v.toLocaleString("es-CL", { maximumFractionDigits: 1 }) : String(v));
const list = (v: unknown) => (Array.isArray(v) ? v.map(String).join(", ") : String(v));

const UNITS: Record<string, string> = { mw: "MW", capacity_mw: "MW", kv: "kV" };
const LABELS: Record<string, string> = { cycles: "ciclos", share: "fracción", policy: "política", template: "plantilla", role: "rol", tech: "tecnología", focus: "foco" };

/** Arguments as one readable line: `{bus: "Antofagasta", mw: 120}` → "Antofagasta · 120 MW". */
export function argsText(name: string, args: unknown): string {
  if (!isObj(args)) return "";
  if (name === "step" && typeof args.cycles === "number") return `${args.cycles} ${args.cycles === 1 ? "ciclo" : "ciclos"} de 5 min`;
  if (name === "repair_lines" && !args.lines) return "todas las líneas abiertas";
  if (name === "prepare_scenario") return scenarioArgs(args);
  if (name === "add_line" && args.a && args.b) {
    const rest = Object.entries(args).filter(([k]) => k !== "a" && k !== "b");
    return [`${args.a} – ${args.b}`, ...rest.map(([k, v]) => part(k, v))].filter(Boolean).join(" · ");
  }
  return Object.entries(args).map(([k, v]) => part(k, v)).filter(Boolean).join(" · ");
}

/** One change in words: "× 0 carbón, gas, diésel", "+120 MW demanda en Antofagasta"; `name` turns ids into names. */
export function changeText(c: Json, name: (id: string) => string = (id) => id): string {
  const own = typeof c.generator_mw === "number" ? c.generator_mw : typeof c.load_mw === "number" ? c.load_mw : null; // a new substation
  const how = own !== null ? `+${num(own)} MW` : typeof c.add === "number" ? `${c.add >= 0 ? "+" : ""}${num(c.add)}${c.target === "population" ? "" : " MW"}` : typeof c.factor === "number" ? `× ${num(c.factor)}` : "";
  const what = Array.isArray(c.tech) && c.tech.length ? c.tech.map((t) => TECHS[String(t)] ?? String(t)).join(", ") : TARGETS[String(c.target)] ?? String(c.target);
  const where = ["places", "comunas", "buses", "areas", "zones", "lines"].flatMap((k) => (Array.isArray(c[k]) ? (c[k] as unknown[]).map((x) => name(String(x))) : []));
  return [how, what, where.length ? `en ${where.join(", ")}` : ""].filter(Boolean).join(" ");
}

/** prepare_scenario's changes in words ("+120 MW demanda en Antofagasta"), then the failures. Before, they read
 * "[object Object], [object Object]". */
function scenarioArgs(args: Json): string {
  const changes = Array.isArray(args.changes) ? args.changes.filter(isObj) : [];
  const words = changes.map((c) => changeText(c));
  const out = (k: string, label: string) => (Array.isArray(args[k]) && (args[k] as unknown[]).length ? [`${label}: ${list(args[k])}`] : []);
  return [...words, ...out("open_lines", "líneas fuera"), ...out("out_buses", "subestaciones fuera")].join(" · ") || "red base";
}

function part(key: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return "";
  if (UNITS[key]) return `${num(value)} ${UNITS[key]}`;
  if (Array.isArray(value)) return list(value);
  if (isObj(value)) return Object.entries(value).map(([k, v]) => `${k} = ${num(v)}`).join(", ");
  if (LABELS[key]) return `${LABELS[key]} ${num(value)}`;
  return num(value);
}

/** One short line from a tool result, or "" when nothing short fits (the detail still shows it). */
export function resultText(name: string, ok: boolean, result: unknown): string {
  if (!ok) return failureText(result);
  if (!isObj(result)) return typeof result === "string" ? result.slice(0, 140) : "";
  if (name === "prepare_scenario") return scenarioResult(result);
  if (name === "find_line" && Array.isArray(result.lines)) return lineResult(result.lines.filter(isObj));
  const parts: string[] = [];
  if (typeof result.id === "string") parts.push(`id ${result.id}`);
  if (typeof result.bus_name === "string") parts.push(`en ${result.bus_name}`);
  if (Array.isArray(result.open_lines)) parts.push(result.open_lines.length ? `líneas abiertas: ${list(result.open_lines)}` : "ninguna línea abierta");
  if (typeof result.load_shed_mw === "number") parts.push(`${num(result.load_shed_mw)} MW sin servir`);
  if (typeof result.dark_buses === "number") parts.push(`${result.dark_buses} barras sin suministro`);
  else if (Array.isArray(result.dark_buses)) parts.push(`${result.dark_buses.length} barras sin suministro`);
  if (name === "step" && Array.isArray(result.cycles)) parts.push(`${result.cycles.length} ${result.cycles.length === 1 ? "ciclo simulado" : "ciclos simulados"}`);
  if (isObj(result.run) && typeof result.run.cycle === "number") parts.push(`ciclo ${result.run.cycle}`);
  if (typeof result.session_id === "string" && (name === "start_session" || name === "join_session")) parts.push(`sesión ${result.session_id.slice(0, 6)}`);
  if (Array.isArray(result.warnings) && result.warnings.length) parts.push(`${result.warnings.length} ${result.warnings.length === 1 ? "advertencia" : "advertencias"}`);
  return parts.join(" · ");
}

/** Where each place went, changes that touched nothing, and the people without power of a simulated failure. */
function scenarioResult(result: Json): string {
  const changes = isObj(result.prepared) && Array.isArray(result.prepared.changes) ? result.prepared.changes.filter(isObj) : [];
  const places = changes.flatMap((c) => (Array.isArray(c.places) ? c.places.filter(isObj).map((p) => String(p.bus_name)) : []));
  const empty = changes.filter((c) => c.matched === 0).length;
  const sim = isObj(result.simulation) && isObj(result.simulation.with_changes) ? result.simulation.with_changes : null;
  return [
    places.length ? `en ${places.join(", ")}` : "",
    empty ? `${empty} ${empty === 1 ? "cambio no tocó" : "cambios no tocaron"} ninguna subestación` : "",
    sim && typeof sim.people_without_power === "number" ? `${num(sim.people_without_power)} personas sin suministro` : "",
  ].filter(Boolean).join(" · ") || "mapa preparado";
}

/** The line find_line found ("R239 · S/E NUEVA MAITENCILLO – S/E NUEVA PAN DE AZUCAR (500 kV)"), or how many matched. */
function lineResult(lines: Json[]): string {
  if (lines.length === 1) return `${String(lines[0].id)} · ${String(lines[0].name)}`;
  return `${lines.length} líneas: ${lines.slice(0, 4).map((l) => String(l.id)).join(", ")}${lines.length > 4 ? "…" : ""}`;
}

function failureText(result: unknown): string {
  if (typeof result === "string") return result.slice(0, 200);
  if (isObj(result)) for (const k of ["error", "detail", "message"]) if (typeof result[k] === "string") return (result[k] as string).slice(0, 200);
  return "La herramienta falló.";
}

/** What the map must reload after a tool: the session network, the cut state, or the run snapshots. */
export type Refresh = "network" | "state" | "snapshots";
const NETWORK_TOOLS = new Set(["start_session", "join_session", "add_datacenter", "add_generator", "add_line", "add_bus", "add_substation", "edit_element", "remove_element", "reset_network"]);
const STATE_TOOLS = new Set(["cut_lines", "repair_lines"]);
export function refreshFor(name: string): Refresh | null {
  if (NETWORK_TOOLS.has(name)) return "network";
  if (STATE_TOOLS.has(name)) return "state";
  if (name === "step") return "snapshots";
  return null;
}

/** Text of an HTTP error before the stream, or of an `error` event inside it (docs/assistant.md sections 2 and 2b). */
export function errorMessage(status: number, retryAfter?: number | null): string {
  switch (status) {
    case 0: return "No se pudo conectar con el servidor. Revisa la conexión e intenta de nuevo.";
    case 404: return "La conversación venció o no existe. Empieza una nueva.";
    case 409: return "Otro mensaje de esta conversación estaba corriendo; reintenta.";
    case 413: case 422: return "El mensaje está vacío o supera 2000 caracteres.";
    case 429: return retryAfter ? `Demasiados mensajes; espera ${retryAfter} s.` : "Demasiados mensajes; espera un momento.";
    case 502: return "El modelo falló; tu mensaje quedó guardado, intenta de nuevo.";
    case 503: return "El asistente no está disponible en este servidor. El resto del mapa funciona sin él.";
    default: return "El asistente falló; reintenta.";
  }
}

/** Notice when a limit stopped the loop before the model finished. */
export function truncatedText(truncated: string | null | undefined): string | null {
  if (truncated === "steps") return "El asistente llegó al máximo de pasos por mensaje y no terminó.";
  if (truncated === "deadline") return "El asistente llegó al tiempo máximo por mensaje y no terminó.";
  return null;
}
