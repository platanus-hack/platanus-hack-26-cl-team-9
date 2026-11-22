import type { PickingInfo } from "@deck.gl/core";
import { formatNumber } from "../lib/format";
import nodeIndexUrl from "../../../data/processed/node_index.json?url";

// Tuples come from data/scripts/build_node_index.py.
type Line = [id: string, kv: number | null, circuit: string, to: string, toId: string, km: number | null, mva: number | null, x: number | null, topology: string, assumption: boolean, kind: string];
type Plant = [name: string, tech: string, mw: number];
type Storage = [name: string, mw: number | null, hours: number | null, equipment: string | null, source: string];
type Comuna = [name: string, population: number, share: number];
type Branch = [name: string, type: string, mva: number | null, xPu: number | null, rPu: number | null];

export interface NodeRecord {
  id: string; name: string; kind: string; kv: number | null; kv_levels: number[]; owner: string | null; system: string;
  segment: string; macro_zone: string; region_code: string; comuna_code: string; lon: number; lat: number;
  in_main_grid: boolean; degree: number; generation_mw: number; served_population: number;
  cen?: { id: number; code: string; scada: boolean; comm: boolean };
  lines: Line[]; plants: Plant[]; plants_count: number; storage: Storage[]; storage_candidates: [number, number];
  comunas: Comuna[]; operating: Record<string, [load: number, gen: number]>; model_buses: [string, number][]; model_branches: Branch[];
}

const MAX_LINES = 14;
const MAX_BRANCHES = 8;
let nodeIndex: Promise<Record<string, NodeRecord>> | null = null;

export function describeTopology(source: string, assumption: boolean): string {
  if (assumption) return "supuesto de acople";
  return source.startsWith("CEN") ? "oficial CEN" : "inferida";
}

/** Why: clicking a substation or generation column must answer "what is this node?" with everything the repo knows. */
export function createNodePopup(container: HTMLElement) {
  const popup = document.createElement("div");
  popup.className = "node-popup";
  popup.hidden = true;
  container.appendChild(popup);
  const onKey = (event: KeyboardEvent) => event.key === "Escape" && (popup.hidden = true);
  document.addEventListener("keydown", onKey);
  return {
    onClick: (info: PickingInfo) => showNodeDetailWorkflow(popup, container, info),
    dispose: () => { document.removeEventListener("keydown", onKey); popup.remove(); },
  };
}

function showNodeDetailWorkflow(popup: HTMLDivElement, container: HTMLElement, info: PickingInfo) {
  const nodeId = _clickedNodeId(info);
  _loadNodeIndex()
    .then((index) => _renderOrHide(popup, container, index[nodeId ?? ""], info))
    .catch((error) => console.error("No se pudo cargar el detalle del nodo", error));
}

function _clickedNodeId(info: PickingInfo): string | null {
  const isNodeLayer = info.layer?.id === "substations" || info.layer?.id === "generation";
  return isNodeLayer && info.object ? (info.object.id as string) : null;
}

function _loadNodeIndex(): Promise<Record<string, NodeRecord>> {
  nodeIndex ??= fetch(nodeIndexUrl).then((r) => r.json());
  return nodeIndex;
}

function _renderOrHide(popup: HTMLDivElement, container: HTMLElement, node: NodeRecord | undefined, info: PickingInfo) {
  popup.hidden = !node;
  if (!node) return;
  popup.replaceChildren(..._card(node, () => (popup.hidden = true)));
  _placeNear(popup, container, info.x, info.y);
}

function _placeNear(popup: HTMLElement, container: HTMLElement, x: number, y: number) {
  const gap = 12, margin = 8;
  const left = Math.max(margin, Math.min(x + gap, container.clientWidth - popup.offsetWidth - margin));
  const top = Math.max(margin, Math.min(y + gap, container.clientHeight - popup.offsetHeight - margin));
  popup.style.left = `${left}px`;
  popup.style.top = `${top}px`;
}

/** Why: the minimum to judge a node (size, supply, people, links) is always visible; the rest of the dictionary sits behind one button. */
function _card(n: NodeRecord, close: () => void): HTMLElement[] {
  const extra = _el("div", "", "extra");
  extra.hidden = true;
  extra.append(
    _section("Ficha", _rows(_fichaRows(n))),
    _section("Almacenamiento", _storage(n)),
    _section("Población por comuna", _population(n)),
    _section(`Líneas conectadas · ${n.lines.length}`, _lines(n)),
    _section("Modelo eléctrico (PyPSA-CL)", _model(n)),
  );
  const toggle = _el("button", "Ver todos los datos", "more");
  toggle.onclick = () => { extra.hidden = !extra.hidden; toggle.textContent = extra.hidden ? "Ver todos los datos" : "Ocultar datos"; };
  return [
    _header(n, close),
    _section("Resumen", _rows(_summaryRows(n))),
    _section(`Generación · ${formatNumber(n.generation_mw, 1)} MW`, _generation(n)),
    _section("Demanda y despacho simulado", _operating(n)),
    toggle,
    extra,
  ];
}

function _summaryRows(n: NodeRecord): [string, string][] {
  return [
    ["Personas atendidas", formatNumber(n.served_population)],
    ["Líneas conectadas", String(n.degree)],
  ];
}

function _header(n: NodeRecord, close: () => void): HTMLElement {
  const head = _el("div", "", "head");
  const button = _el("button", "×", "close");
  button.onclick = close;
  head.append(_el("strong", n.name), button);
  const sub = _el("div", `${n.id} · ${n.kind === "tap" ? "Derivación" : "Subestación"} · ${n.kv_levels.join(" / ")} kV`, "sub");
  const wrap = _el("div", "", "top");
  wrap.append(head, sub);
  return wrap;
}

function _fichaRows(n: NodeRecord): [string, string][] {
  return [
    ["Propietario", n.owner ?? "s/d"],
    ["Sistema", `${n.system} · ${n.segment}`],
    ["Zona / región / comuna", `${n.macro_zone} · ${n.region_code} · ${n.comuna_code}`],
    ["Coordenadas", `${n.lat.toFixed(4)}, ${n.lon.toFixed(4)}`],
    ["Red principal", n.in_main_grid ? "Sí" : "No (aislada)"],
    ["Líneas (grado)", String(n.degree)],
    ["Código CEN", n.cen?.code ? `${n.cen.code} · SCADA ${n.cen.scada ? "sí" : "no"}` : "s/d"],
  ];
}

function _generation(n: NodeRecord): HTMLElement {
  const rows = n.plants.map(([name, tech, mw]): [string, string] => [name, `${tech} · ${formatNumber(mw, 1)} MW`]);
  const more = n.plants_count > n.plants.length ? `+${n.plants_count - n.plants.length} plantas más` : "";
  return _stack(n.plants_count ? _rows(rows) : _note("Sin plantas conectadas"), _note(more));
}

function _storage(n: NodeRecord): HTMLElement {
  const [count, mw] = n.storage_candidates;
  const named = n.storage.map(([name, mwi, hours, equipment]): [string, string] => [name, `${equipment ?? ""} ${formatNumber(mwi, 1)} MW · ${formatNumber(hours, 1)} h`.trim()]);
  const candidates = count ? `${count} candidatos del modelo PyPSA-CL (${formatNumber(mw)} MW). No confirmados como existentes: no contar como batería real.` : "";
  return _stack(named.length ? _rows(named) : _note("Sin almacenamiento nombrado"), _note(candidates, "warn"));
}

function _population(n: NodeRecord): HTMLElement {
  const rows = n.comunas.slice(0, 6).map(([name, pop, share]): [string, string] => [name, `${formatNumber(pop)} hab · ${Math.round(share * 100)}%`]);
  return _stack(_rows([["Atendidos directamente", formatNumber(n.served_population)]]), rows.length ? _rows(rows) : _note("Nodo de transmisión: no abastece comunas"));
}

function _lines(n: NodeRecord): HTMLElement {
  const rows = n.lines.slice(0, MAX_LINES).map((l): [string, string] => [
    `${formatNumber(l[1], 1)} kV ${l[2]} → ${l[3]}`,
    `${formatNumber(l[5], 1)} km · ${formatNumber(l[6])} MVA · ${describeTopology(l[8], l[9])}`,
  ]);
  const more = n.lines.length > MAX_LINES ? `+${n.lines.length - MAX_LINES} líneas más` : "";
  return _stack(_rows(rows), _note(more), _note("s/d = dato no disponible en las fuentes"));
}

const POINT_LABELS: Record<string, string> = {
  "feb2025-1500": "Feb 2025 15:00", "feb2025-0300": "Feb 2025 03:00", "nov2026-1300": "Nov 2026 13:00", "nov2026-2000": "Nov 2026 20:00",
};

function _operating(n: NodeRecord): HTMLElement {
  const rows = Object.entries(n.operating).map(([id, [load, gen]]): [string, string] => [POINT_LABELS[id] ?? id, `consume ${formatNumber(load, 1)} · genera ${formatNumber(gen, 1)} MW`]);
  const note = "Demanda: perfil modelado de PyPSA-CL. Despacho: simulado con supuestos. No son valores medidos.";
  return _stack(rows.length ? _rows(rows) : _note("Sin barra eléctrica asociada"), _note(note, "warn"));
}

function _model(n: NodeRecord): HTMLElement {
  if (!n.model_buses.length) return _note("Este nodo no está en el modelo eléctrico");
  const buses = n.model_buses.map(([name, kv]): [string, string] => [name, `${kv} kV`]);
  const branches = n.model_branches.slice(0, MAX_BRANCHES).map((b): [string, string] => [b[0], `${b[1]} · ${formatNumber(b[2])} MVA · x ${formatNumber(b[3], 4)} pu`]);
  const more = n.model_branches.length > MAX_BRANCHES ? `+${n.model_branches.length - MAX_BRANCHES} ramas más` : "";
  return _stack(_rows(buses), _rows(branches), _note(more));
}

function _section(title: string, body: HTMLElement): HTMLElement {
  const section = _el("section");
  section.append(_el("h4", title), body);
  return section;
}

function _rows(rows: [string, string][]): HTMLElement {
  const box = _el("div", "", "rows");
  for (const [label, value] of rows) {
    const row = _el("div", "", "row");
    row.append(_el("span", label), _el("span", value, "val"));
    box.append(row);
  }
  return box;
}

function _stack(...children: HTMLElement[]): HTMLElement {
  const box = _el("div");
  box.append(...children);
  return box;
}

function _note(text: string, kind = ""): HTMLElement {
  const note = _el("div", text, `note ${kind}`.trim());
  note.hidden = !text;
  return note;
}

function _el(tag: string, text = "", className = ""): HTMLElement {
  const el = document.createElement(tag);
  el.textContent = text;
  if (className) el.className = className;
  return el;
}
