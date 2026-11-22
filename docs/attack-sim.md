# Cyberattack simulation extension

Status: **implemented 2026-11-22 (issue #74)** as a thin layer over the strategic theatre; the team decision of section 9 is still pending. Sections 1, 2, 4 and 6-8 stay valid. Sections 3 and 5 describe the first proposal (`plant_out`, `fleet_out`, `/attacks/simulate` with free effects), which was **not** built: see section 3.1 for what exists. Read `idea.md` and `stack.md` first.

> **Overlap with what exists (added 2026-11-21, branch `feat/strategic-sim-api`).** The strategic theatre (`strategy.md`, `mapa3.md` section 10) already runs on the mapa 3 network (188 buses, not 10-14 nodes) and its cascade engine. Through `POST /api/v1/sim/runs/{id}/events` a user or a script can already trigger effect-level events on that network: `C1_generation_loss` on a bus `B###` (its generation, close to E1 `plant_out` at substation level), `C2_common_mode_loss` by zone and technology (close to E2 `fleet_out`), and `C3_transmission_opening` on a line `R###` or corridor (E3 `line_open`). It has no plant-level ids and no storage outage, and it keeps the same guardrails (no ranking, no worst-case search, the adversary acts by area only). If the team approves this extension, build the catalog and `/attacks/*` as a thin layer over those events rather than a second engine path.

## 1. What this adds

CascadaSEN also replays **documented cyber incidents against power systems** as grid disturbances. A bounded catalog of scenarios, each tied to a real incident from the last months, is exposed through a local API so that real agents (LLM agents or scripts) can submit an attack scenario and read back what the grid does: islands, load lost, people without power, and what would have mitigated it.

This is not a vulnerability finder and not an optimiser. Nobody asks "which cut does the most damage". The question stays the one in `idea.md`: what happens if this element fails, and what would have prevented it. The new part is that the cause of the failure can be a cyber incident, and that the trigger can come from an external agent through the API.

Why it fits the track: it simulates something that cannot be tested on the real grid, in a reduced digital twin, and the run teaches something that is not visible at a glance (most incidents are small, a few reach the whole country, and the defences decide which).

## 2. Incidents that anchor the scenarios

Only effects on the grid are modelled. Attack techniques are not modelled and not documented here.

| # | Incident | What happened (from public reports) | Effect type in the model |
|---|---|---|---|
| 1 | **Huatacondo, Chile** (Tarapaca), 26-27 Aug 2026 | The 103 MW solar plant and its 98 MW / 312 MWh battery were disconnected from the SEN. The CEN activated its disconnection protocol and recorded the cause as a cyberattack (forced disconnection request SDCF 2026100475). On 14 Nov both still showed 0% availability. The investigation is open and a lawmaker asked two ministries for details on 11 Nov. Sources: [pv magazine](https://www.pv-magazine.com/2026/11/17/chilean-pv-plant-hit-by-cyberattack-remains-disconnected/), [ESS News](https://www.ess-news.com/2026/11/17/chile-solar-plus-storage-plant-remains-offline-after-cyberattack/), [T13](https://www.t13.cl/noticia/nacional/ciberataques-chile-ataque-dejo-desconectada-una-planta-electrica-encendio-las-a-16-11-2026) | E1: plant (and storage) forced out for a long time |
| 2 | **Poland**, 29 Dec 2025 | Coordinated attacks on 30+ wind and solar farms, a combined heat and power plant serving about 500,000 customers and a manufacturing company. The activity focused on grid connection point substations and disrupted communications at the sites. CERT Polska reports default credentials, no MFA and exposed edge devices. Attribution differs: CERT Polska names Berserk Bear, ESET and Dragos say Sandworm with medium confidence. A follow-up report in Aug 2026 found it more complex. Sources: [CERT Polska report](https://cert.pl/uploads/docs/CERT_Polska_Energy_Sector_Incident_Report_2025.pdf), [CISA](https://www.cisa.gov/news-events/alerts/2026/02/10/poland-energy-sector-cyber-incident-highlights-ot-and-ics-security-gaps), [Dragos](https://www.dragos.com/blog/poland-power-grid-attack-electrum-targets-distributed-energy-2025) | E2: many distributed plants lose control or output at once |
| 3 | **UK**, July 2026 | A small power generator was offline for four days after a reported cyberattack, linked to Iran by The Telegraph. The wider supply was not affected and technical details are unknown. Sources: [Help Net Security](https://www.helpnetsecurity.com/2026/08/24/uk-power-plant-cyberattack/), [TrendAI](https://www.trendaisecurity.com/en-us/resources-insights/trendai-security-blog/uk-power-facility-cyberattack-shutdown-what-critical-infrastructure-operators-and-defenders-need-to-know) | E1, short and small: a useful counter-example |
| 4 | **US**, July 2026 | Water and wastewater utilities hit through programmable logic controllers, after a CISA warning about Iranian-affiliated actors targeting PLCs ([AA26-097a](https://www.cisa.gov/news-events/cybersecurity-advisories/aa26-097a)). Not a power incident. Kept only as context for the control-device class of E3. | E3 (context only) |
| 5 | **Reference, not a cyber case:** 25F, Feb 2025 | The blackout started with an unauthorised intervention on a protection device (`idea.md` [3]). Nothing says it was a cyberattack. It is the closest real example of a protection or control manipulation opening a critical line. | E3: spurious line opening |

Left out on purpose:
- **Spain SIPS data theft (7 Sep 2026):** no physical effect on the grid.
- **Attacks on residential inverters, batteries and EV chargers from a DOE/CISA assessment (Aug 2026):** found in one secondary source only. Do not model or quote it until someone checks the primary document.

### Effect types

| Type | Effect in the model | Parameters |
|---|---|---|
| E1 `plant_out` | A plant, and optionally its storage, produces 0 MW for the whole run | plant ids |
| E2 `fleet_out` | Several plants in one zone lose output at the same instant | up to 20 plant ids |
| E3 `line_open` | A line opens without a physical fault | line ids |

## 3. Catalog and API (backlog, local only)

Same rules as `stack.md`: the engine is the only place with physics, the frontend reads `timeline.json`. The attack API is a thin layer over the engine.

```
GET  /api/v1/attacks/catalog
     -> scenarios: id, title, incident, date, effect type, element ids, source links

POST /api/v1/attacks/simulate
     { "scenario": "huatacondo-2026" }
     or
     { "effects": [ { "type": "plant_out", "ids": ["P..."] } ] }
     -> summary (islands, load shed MW, people without power),
        timeline (same format as stack.md section 6),
        mitigations (what would have prevented it)
```

Rules for the API:
- Binds to `127.0.0.1` only. If the team ever exposes it, require an API key from an environment variable and a rate limit. Never commit keys.
- At most 3 effects and 20 ids per request. Ids must exist in the public layers under `data/processed/geo/`. Anything else returns 422.
- There is no endpoint that ranks targets, sweeps all pairs or returns a "worst case". The N-2 sweep in `idea.md` section 6 stays an offline validation tool.
- Every response says "simulated consequence on a reduced network, not a prediction".
- Each request is logged with the agent name and a seed, so a run can be reproduced.

An external agent can still loop over targets by itself. The API cannot prevent that, and the layers it reads are already public. The mitigation is scope: a bounded catalog, small requests, local binding and no aggregate "most dangerous" output.

### 3.1 What is implemented (2026-11-22)

Catalog: `backend/src/cascadasen/domain/theater/params/incidents.yaml`. Each incident is a theatre template (same shape as `templates.yaml`: scenario events with cycle, adversary off, horizon 24, a policy A/B/C chosen at launch) plus public metadata: title, date, `kind` (`cyber_documented` or `reference_not_cyber`), `verified`, linked sources, notes and the mitigations that would have helped (defensive action ids). `theater_config().incidents` holds the metadata and `.templates` also holds every incident, so `POST /sim/runs` with `template: huatacondo-2026` works too.

| Scenario id | Events (all abstract, zone or area level) | Result at `nov2026-1300` (policy C) |
|---|---|---|
| `huatacondo-2026` | cycle 2: `C1_generation_loss` A01 with `mw: 88.1` (dataset value; the press says 103 MW), `C5_remote_dispatch_loss` A08. The battery is not modelled (not in `storage.geojson`) | L0 in seeds 1-8, scripted (V10, `cyber.md` section 7) |
| `polonia-2025` | cycle 2: `C2_common_mode_loss` in zone NC for solar and for wind (share 0.5 each), `D4_comms_loss` A06 | L1 to L2, millions of people at the peak |
| `reino-unido-2026` | cycle 2: `C1_generation_loss` A09, 40 MW. **Unverified** (press only) | L0, the counter-example |
| `25f-referencia` | cycle 2: `C3_transmission_opening` corridor A06-A07 at `feb2025-1500`. Labelled "not a cyber case" | L3 |

The sizes of Polonia and Reino Unido are replay assumptions (`is_assumption`), not reconstructions.

API (agent routes, in `docs/openapi/agents.openapi.json`):
- `GET /api/v1/attacks/catalog` (`get_attack_catalog`): the list, in file order, with sources, effects and notices. Not ranked.
- `POST /api/v1/sessions/{sid}/attacks/runs` (`start_incident_run`): `{scenario, policy="C", seed?, duration_h?, uncertainty?, stochastic=false, adversary?}`. `stochastic` is **off by default**: the incident is the script, so the card is the incident's own; with the theatre's chance on, unplanned external events also count (seed 6 turned the 40 MW UK counter-example into L2). It builds a normal session run from the template (same limits: 20 runs per session, write rate limit) and returns the run summary. Unknown scenario gives 422 with `valid`. The session's point must equal the incident's `operating_point` (in the catalog): otherwise 422 `{field: "scenario", valid: [<point>]}`, so `25f-referencia` needs a session created with `point: feb2025-1500`. There is no endpoint that accepts free effects, loops over targets or returns a worst case.
- `step_run`, `get_run_report`, `get_run_after_action`, `replay_run` are the existing routes. The report has an `incident` block: public metadata, mitigations, and a `consequence_card` (level, `people_without_power`, `load_shed_mw`, `unserved_energy_mwh`, `failure_cost_usd`, `outage_duration_h` with `is_assumption: true`). MWh and cost extrapolate the **peak** unserved power over `duration_h` (default 4 h from `incidents.yaml` `defaults`, editable per run via `duration_h`), because the theatre horizon is about two hours. The standard indicators (TTU, mission continuity, wrong decisions, reserve) stay in `indicators`.
- The after-action (`TemplateInterpreter`) adds an `incident` section: summary, effect, prevention lines (from `narrative_es.yaml` `prevention`), notes, sources. `ClaudeInterpreter` may still rewrite the narrative; it only explains.
- Web: the **Incidentes** view of mapa 3 consumes this API. It creates a session at the incident's hour when needed and plays the cycles' `transient` on the map (`mapa3.md` section 4.2).
- MCP and assistant tools: `list_incident_scenarios` and `start_incident_run(scenario, policy, seed, duration_h)` (`docs/mcp.md`).

Every result carries "Escenario hipotético: se modela el efecto, no el ataque." and "Consecuencia simulada en una red reducida, no una predicción." Tests: `backend/tests/unit/test_incidents.py`.

## 4. Demo

On the map (`web/`):
1. The user picks "Huatacondo 2026" (or an agent submits it). The plant column drops and the battery with it.
2. The counter shows how little the SEN notices: one 100 MW plant does not black out a 38 GW system.
3. Switch to the Poland scenario: many plant columns drop together in one zone, and the model shows whether the island holds.
4. Switch to `line_open` on the 25F corridor: the national cascade from `idea.md`.

The contrast is the message: documented cyber incidents so far have been small for the grid, and one protection-level failure was enough for a national blackout. Keep that framing honest in the pitch.

Chile hook: Huatacondo is a current Chilean case, still offline. Do not attribute it to any actor. The investigation is open.

## 5. Dependencies and phasing

| Phase | Needs | Delivers |
|---|---|---|
| A | Cascade engine with plant outage (`plan.md` phase 6) | `plant_out` and `line_open`; catalog with Huatacondo and the 25F reference |
| B | Phase A | `fleet_out` (Poland) |
| C | Phase A | Mitigations list: batteries and defence schemes that change the result |
| D | Optional | Example agent script that calls the API with the catalog |

Priority P2 in `plan.md`. Do not start before the 25F replica works (checkpoint Sat 14:00).

The existing `POST /graph/islands` in the backend removes lines or whole substations (ids `L...`, `T...`, `SE...`). It does not remove one plant. Removing the substation node would drop everything attached to it. So `plant_out` cannot be built on that endpoint alone and needs the engine.

## 6. Data check done on the repo

- `data/processed/geo/plants.geojson` has a `HUATACONDO` plant: solar, **88.1 MW**, node `SE1893` (S/E Lagunas, 220 kV). The news reports 103 MW. The difference is not explained: show the repo value with the label "dataset value" and mention the reported figure.
- No storage record with the name Huatacondo was found in `storage.geojson` by name. The 98 MW / 312 MWh battery may be absent or listed under another name. Check before promising it in the demo.

## 7. Guardrails

- Model consequences only. No attack techniques, no vulnerabilities, no CVEs, no credentials, no IP addresses, no tooling, no step-by-step. Reject pull requests that add them.
- No public ranking of weak points. Public outputs stay at zone level where possible.
- Language: "simulated incident", "failure", "scenario". Avoid "hack" and "attack the grid" in the UI.
- Sources: link each scenario to its public report. Mark anything unverified as "unverified".
- If someone from the CEN or a mentor objects, drop the API and keep the catalog as a replay without external input.

## 8. Limits

- Reduced network of about 10-14 nodes. Results are orders of magnitude, not forecasts.
- The real incidents are not fully known. The scenarios replay an assumed effect (plant out, fleet out, line open). They do not reconstruct what happened.
- Cause-and-effect between an incident and a grid event is only as good as the public reports. Several are press-based and some details are unknown.
- Frequency is modelled, voltage mostly is not (`idea.md` section 5).

## 9. Decisions for the team

1. Confirm the reversal of the `idea.md` line "Do not build an attacker feature": allowed only as a bounded replay of documented incidents, never as an optimiser.
2. API local only (recommended) or exposed.
3. Whether the pitch uses Huatacondo as the Chilean hook.
4. Owner. Suggested: whoever owns the engine API (Alonso), after phase 6.
