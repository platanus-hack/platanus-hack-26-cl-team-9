# Plan 2.0: an agent that understands, edits and tests the network

Last updated: 2026-11-21. Status: **proposal, not built**. Part 2.0 of `plan.md`. Read `architecture.md` (how the system is built), `engine.md` (the physics) and `minimum-dataset.md` (what the engine needs) first.

Tags: EVIDENCE = read from code, data or a measured run. ASSUMPTION = a proposal or a guess that the team has not confirmed.

## 1. Goal

Plan 1.0 answers "what happens if this line is cut". Plan 2.0 answers "what happens if the network changes, and how do we fix it".

An agent that works on the map of Chile in four steps:

1. **Understands** the network: where generators go, who consumes, and the state of the grid.
2. **Edits nodes**: lower what a plant produces, change the population of a consumer.
3. **Runs simulations on its edits and proposes fixes**: "the population here doubled, does something break, and what do we build so the network stays healthy".
4. **Shares a table panel** with the human engineer, who can group nodes and apply the same edits by hand.

All four use one mechanism, the **change set** (section 4). The agent and the table panel never change the network in different ways.

## 2. What the user asked, and the answers

### 2.1 The three components and the panel

| # | Component | What it is in this plan | Section |
|---|---|---|---|
| 1 | The agent knows the rules | Read-only tools and a rules file: siting of generators, consumer classes, network state | 5.1 |
| 2 | The agent edits nodes | Edit generation or demand of nodes into a draft. The agent never edits lines | 5.2 |
| 3 | The agent edits, simulates and proposes fixes | Run the engine on the draft, measure health, propose plants, storage or lines, and long-term scenarios (2050) | 5.3 |
| 4 | Table panel | Nodes grouped by any attribute, with bulk edits, that produces the same change sets | 5.4 |

### 2.2 The question about lines: are they only calculated?

**Yes for flows, no for the line itself.** EVIDENCE (`flow.py`, `network.py`):

| Element | Attribute | Input or output | Can the agent edit it? |
|---|---|---|---|
| Node | generation `gen` (MW), by carrier | Input | Yes (component 2) |
| Node | demand `load` (MW), people served | Input | Yes (component 2) |
| Node | synchronous MW and inertia | Derived from the plants online at the node | No directly; it changes when plants change |
| Line | **flow** (MW) and **loading** (% of capacity) | **Output** of the DC flow | **No.** It is computed |
| Line | capacity (MW), reactance `x_pu`, voltage | Input (a physical property of the cable) | Not as a direct edit (component 2). Only as a **proposal** that the engineer approves (component 3: "add a cable here", "upgrade this one") |
| Network | which lines exist (topology) | Input | Only as a proposal (component 3) |

"Computed from the elements around it" is true, with one correction: the DC flow solves the whole connected island, not only the neighbours. A change at one node moves flow over every path that connects it to the rest. So an edit near Santiago can overload a line in the Maule region.

Rule for this plan: **injections can be edited freely, the cable cannot; changes to the cable are design proposals, labelled with a cost.**

## 3. What exists today and what is missing

### 3.1 To reuse (EVIDENCE: `architecture.md`)

| Piece | Where | Use in 2.0 |
|---|---|---|
| Cascade engine, 188 buses, 273 lines | `domain/cascade/` | Runs every draft. A single cut takes 29 ms and the full N-1 sweep of 273 cuts takes 2.0 s (measured, `nov2026-2000`), so a draft can be tested in seconds |
| DC-OPF secure base case | `data/scripts/build_baseline_opf.py` (scipy HiGHS) | Re-dispatch after an edit (needs to run in the backend, see 3.2) |
| LLM adapters (Claude API, Bedrock) | `infrastructure/llm.py`, ports in `domain/ports.py` | The agent's model. Off by default (`CASCADASEN_LLM_ENABLED`) |
| Action validator, audit log, replay from a recipe | `domain/theater/` | The same discipline: validate before executing, log every action, replay with the recorded LLM picks |
| Parameters with provenance in YAML | `domain/*/params/` | Siting rules, costs and health thresholds follow the same rule: a source or `is_assumption: true` |
| Map, tabs, node detail, scenarios selector | `web/src/cascade/` | Place for the panel, the chat and the diff on the map |
| Plants with technology and MW (1,245) | `data/processed/geo/plants.geojson`, `node_index.json` | Base for per-carrier edits |

The theatre agents (`domain/agents/`: C2, ISR, Operations...) defend the grid during an attack. The planning agent of 2.0 is another agent, with another job: planning and what-if analysis. It shares the engine, the LLM port and the audit trail, and nothing else.

### 3.2 Gaps that block the plan

| # | Gap | Evidence | Needed for |
|---|---|---|---|
| G1 | Generation is stored per bus, not per bus and carrier. The base case has `gen_by_bus`, `sync_mw_by_bus` and `gen_by_carrier_mw` for the whole system | `baseline_opf.json` keys | "Lower what this plant produces", "hydro +50%" |
| G2 | The secure dispatch (OPF) is an offline script. The engine cannot re-dispatch after an edit | `build_baseline_opf.py` is run by hand and needs `scipy`, which is not in the repo dependencies | Any edit to generation or demand |
| G3 | Demand is not a function of population. Load comes from PyPSA-CL `Loads.xlsx` per bus and `people` comes from the INE comunas, with no link between them | `scenario.py` | "The population here doubled" |
| G4 | `people` is wrong in some substations: load with 0 people (23 substations above 20 MW at `feb2025-1500`, 22% of demand) | `docs/minimum-dataset.md` section 1.5 | Component 3 (population edits). Fix before using it |
| G5 | There is no consumer class (residential, commercial, mining, industrial). In the north, load is mostly mining, which does not follow population | ASSUMPTION: the data has no class; to check in `Loads.xlsx` | A realistic demand model |
| G6 | No siting data: rivers and flows, solar and wind resource, protected areas, distance to a substation | Not in `datasets.md` | "There is water nearby, add a hydro plant" |
| G7 | No cost model in the engine | PyPSA-CL has `Costs.xlsx` (`datasets.md` source 32) but nothing reads it for planning | Comparing fixes by cost |
| G8 | No definition of "network health" | None in the repo | The fix loop needs a stopping criterion |
| G9 | Results are precomputed static files. A draft needs the backend | `web/public/cache/`; issue #34 moves them to the backend | Everything that edits |
| G10 | Cache and engine are out of date with each other | `docs/escenarios.md` section 6 | A trusted baseline to compare against |

## 4. The core mechanism: the change set

A **draft** is a copy of a base case plus a list of edits. The engine runs on the draft. Base data is never modified.

```
base case (point + network)  ─┐
                              ├─► apply(change set) ─► draft network + operating point ─► re-dispatch (OPF) ─► engine
change set (list of edits) ──┘                                                                       │
                                                                                                     ▼
                                                  health + diff against the base case ◄──────────────┘
```

A change set is plain data (JSON), so the agent, the panel and a test can all create it:

```json
{
  "base": "nov2026-2000",
  "edits": [
    { "op": "scale_generation", "select": {"carrier": "hydro", "zone": "centro_sur"}, "factor": 1.5 },
    { "op": "scale_population", "select": {"node": "B043"}, "factor": 2.0 },
    { "op": "add_plant", "node": "B043", "carrier": "hydro ROR", "mw": 50 }
  ],
  "reason": "free text, shown in the audit log"
}
```

Edit types:

| Op | Effect | Allowed to | Kind |
|---|---|---|---|
| `scale_generation` / `set_generation` | Change MW of a carrier at the selected nodes | Agent and panel | Direct edit |
| `scale_population` / `set_load` | Change people (and so demand) or MW of the selected nodes | Agent and panel | Direct edit |
| `set_availability` | Take a plant out or limit it | Agent and panel | Direct edit |
| `add_plant`, `add_storage` | A new generator or battery at a node | Agent proposes, human approves | Design proposal, with cost |
| `upgrade_line`, `add_line` | More capacity on a line, or a new line between two nodes | Agent proposes, human approves | Design proposal, with cost |
| `scale_fleet` | A carrier scaled across the whole country (for example "hydro 50%, solar 30% more in 2050") | Agent and panel | Scenario |

Rules:

- **Validation before executing.** Ranges (no negative MW, no more than installed capacity, no edit of a line flow), units and existing ids. A rejected edit returns the reason to the agent, which corrects it.
- **Selectors, not lists.** `select` takes node ids or attributes (zone, voltage, carrier, region, class, loading above X%). The same selector language is the filter of the table panel.
- **Every edit is logged** (who, when, why) in the hash-chained audit log, and a draft can be replayed from its change set and the seed.

## 5. The four pieces in detail

### 5.1 Component 1: the agent knows the network

**Goal:** the agent answers questions and reasons from real data. It does not guess.

- **Read-only tools** (the agent calls them; it never computes physics itself):
  - `get_node(id)`, `find_nodes(selector)`, `group_nodes(by, aggregates)`;
  - `get_state(point)` (generation, load, loading per line, islands);
  - `get_health(draft)`;
  - `explain_rule(topic)`.
- **Rules file** `domain/planning/params/rules.yaml`, with provenance. It holds what the user called "how generators are placed" and "who consumes":
  - generator siting by carrier (resource needed, minimum and maximum size, connection voltage, maximum distance to a substation);
  - consumer classes and how demand follows population;
  - operating limits (loading at or below 100% in N-0, frequency band, the 31,000 MWs inertia floor of the base case).
  Rules without a source are marked `is_assumption: true`, as everywhere in the repo.
- **Grounding:** every number the agent states must come from a tool result of the same turn. The reply carries the references.
- **Acceptance:** a set of at least 30 questions with known answers ("which substations are above 90% loading at the evening peak", "how much hydro is online") passes with no invented numbers.

### 5.2 Component 2: the agent edits nodes

**Goal:** from a sentence to a validated draft.

- **Flow:** the user writes "lower the hydro of the Maule region by 30%". The agent calls `find_nodes`, builds a change set, validates it, shows the **diff** (MW before and after per node, total effect), and waits for the user to **confirm**. Nothing runs without confirmation by default.
- **Scope:** nodes only (generation, population, demand, availability). **Lines are out of scope** (section 2.2).
- **Undo:** each draft keeps its history; the user can remove an edit or go back.
- **Acceptance:** the examples in section 8 produce the expected change set; invalid requests are explained, not applied.

### 5.3 Component 3: run, find what breaks, propose fixes

**Goal:** close the loop between an edit, its consequences and a fix.

**Step 1: consequences.** After an edit the backend re-dispatches (OPF), then measures the draft:

- N-0: lines above 100% loading (the secure base case has none);
- N-1 sweep (2.0 s measured): how many of the 273 single cuts still lose no load, against the base case (EVIDENCE: 219 to 238 of 273 lose none, depending on the hour);
- frequency: inertia online against the floor, and the cascade result of the worst cuts, reported by effect;
- unserved energy and people.

**Step 2: network health.** ASSUMPTION: a vector, not a single number, with a traffic light per item.

| Item | Healthy if | Source of the threshold |
|---|---|---|
| Overloaded lines at N-0 | none | NTSyCS art. 5-27 (100% of capacity), in `engine.md` |
| N-1 resilience | not worse than the base case of the same hour | Base case |
| Inertia online | at or above 31,000 MWs | Floor of `build_baseline_opf.py` |
| Reserve margin | positive | ASSUMPTION |
| Unserved load under the worst single cut | not worse than the base case | Base case |

The thresholds are the team's decision (section 10, question 3).

**Step 3: propose fixes.** The agent searches a **remedy catalog**; the engine scores every candidate; the agent chooses and explains.

| Remedy | Example | Needs |
|---|---|---|
| Add a plant where the resource exists | "there is a river 8 km from this substation: a small run-of-river hydro, 30 MW" | Siting data (gap G6), cost (G7) |
| More generation or storage at a node | "give substation X more power": more MW or a battery at the node | Cost model |
| Upgrade a line | More capacity on the line that overloads first | Cost per km |
| Add a line | A new cable between two nodes that relieves a corridor | Cost per km, route |
| Redispatch | Move generation between existing plants | Nothing new |

The loop: apply a candidate, run, re-measure, keep the best, repeat until the health is acceptable or a budget runs out (for example 40 simulations, about a minute at the measured speed). The result is a short list of options with cost and health, not one answer, plus the reasoning in Spanish.

**Step 4: long-term scenarios.** "In 2050 hydro produces 50% and solar 30% more": `scale_fleet` edits per carrier, then OPF, then the same measurement. ASSUMPTION: the starting values of such scenarios should come from an official source (for example the long-term energy planning scenarios of the Ministerio de Energía; not verified), not from the agent.

**Honest limits:** DC flow has no voltage, so a fix that looks good in DC can fail on voltage (the same limit as the 25F, `engine.md`). Every proposal carries that warning. The agent proposes; an engineer decides.

### 5.4 Component 4: table panel

**Goal:** an electrical engineer works by hand, with the same power as the agent.

- **Location:** a new tab **Nodos** in the sidebar (and "Escenarios" in the rail for the list of drafts), next to Red and Simulación.
- **Table:** one row per node, with the columns the user picks (the "data under the filter" principle of `minimum-dataset.md`). Default columns: name, voltage, zone, generation, demand, people, loading of its worst line.
- **Group by** any attribute (zone, voltage, region, carrier mix, consumer class, loading band), with sum, mean and count per group.
- **Select and filter:** the same selector language as the change sets. Selecting rows highlights them on the map; clicking a node on the map selects its row.
- **Bulk edit:** "raise the generation of every substation with these features by 40%". The form builds a change set, shows the diff, and runs it. The user can also type it to the agent.
- **Drafts:** create, name, compare against the base case (a table of differences and the health vector), duplicate, export and import as JSON. A draft can be shared as a link.
- **Map:** changed nodes get a marker; the lines show the loading of the draft; a toggle switches between base and draft.
- **Works without the LLM.** The panel is plain engine and API; only the chat needs the model.

## 6. Architecture

Same hexagonal rules as `architecture.md`: `domain/` imports nothing from the outside.

```
backend/src/cascadasen/
  domain/planning/
    changeset.py      model, selectors, validation
    apply.py          change set -> draft network and operating point (never mutates the base)
    dispatch.py       runtime DC-OPF after an edit
    health.py         the health vector, N-1 sweep, diff against the base case
    remedies.py       remedy catalog and siting rules
    demand.py         demand as a function of population (consumer classes)
    params/rules.yaml siting, classes, limits, costs (with provenance)
    tools.py          agent tool definitions (read tools and edit tools)
  application/plan_drafts.py     use cases: create draft, edit, run, diff, undo
  api/plan_routes.py             HTTP
  infrastructure/llm.py          reuse the Claude / Bedrock adapters (new port: PlanningAdvisor)
web/src/planning/                Nodos tab, drafts, diff on the map, chat
```

HTTP, under `/api/v1/plan` (ASSUMPTION: names to review):

| Endpoint | What |
|---|---|
| `POST /plan/drafts` | New draft from a base point |
| `PATCH /plan/drafts/{id}/edits` | Add or remove edits (validated) |
| `POST /plan/drafts/{id}/run` | Re-dispatch, simulate, return health |
| `GET /plan/drafts/{id}/diff` | Difference against the base case |
| `GET /plan/nodes?group_by=&filter=` | Table data |
| `POST /plan/agent/messages` | Chat turn (streams tool calls and the proposal) |

**Determinism:** the engine is deterministic. The agent is not. A draft is replayed from its change set; an agent session is replayed from its recorded tool calls and model replies, as the theatre does.

**Guardrails** (`cyber.md` section 8 still applies):
- the agent reports consequences by effect and does not rank targets from an attacker's point of view;
- edits stay in drafts; the base data and the published results never change;
- every simulation request has a budget (count and time);
- the model can be off: everything except the chat keeps working.

## 7. Phases

Hour estimates are rough, for one person, without measurement.

| Phase | Content | Depends on | Rough size |
|---|---|---|---|
| **P0 Foundations** | G1 per-carrier generation table; G2 runtime OPF (add `scipy` to the dependencies); G3 and G4 demand model and fix of `people`; G10 regenerate the baseline with a decision on the engine version; change-set model, validation and `apply` | Issue #34 for serving drafts | 3 to 4 days |
| **P1 Table panel and drafts** (component 4) | API for drafts, nodes and diff; the Nodos tab; map highlight; bulk edit | P0 | 3 days |
| **P2 Knowledge** (component 1) | Rules file, read tools, grounded chat in read-only mode, question set | P0 | 2 days |
| **P3 Agent edits** (component 2) | Edit tools, diff and confirmation, undo | P1, P2 | 2 days |
| **P4 Run and fix** (component 3) | Health vector, N-1 sweep on drafts, remedy catalog, search loop, costs, 2050 scenarios | P0, G6, G7, G8 | 5 days |
| **P5 Quality** | Evaluation sets, audit and replay, docs, demo script | all | 2 days |

P1 comes before the agent on purpose: the panel gives value without a model, and it tests the change-set path that the agent will use.

## 8. Examples and acceptance

1. **Population doubles** at Charrúa (`B043`): edit `scale_population` x2 for the node. Expect the demand of the node to rise by the demand model, the OPF to re-dispatch, and the health vector to say what changed (which lines go above 100%, the N-1 count). The agent then proposes fixes, with cost and the new health.
2. **A plant produces less**: lower the hydro of a zone by 30%. Expect the diff by node, the re-dispatch and the effect on the evening peak.
3. **Siting**: "there is water here, add a basic hydro plant". The agent checks the resource near the node, proposes a size, applies it to a draft and measures.
4. **2050**: hydro x1.5 and solar x1.3 across the country, then the full measurement. Expect a health vector and the lines that become the bottleneck.
5. **By hand**: in the panel, group substations by zone and raise generation by 40% for one group. Expect the same change set as if the agent had built it.

Done for the plan: the five examples run end to end in the browser, the change sets are logged and replayable, the health vector is documented, and the model-off mode works.

## 9. Risks

- **The demand model (G3, G5) can mislead.** Population does not drive mining load. Mitigation: consumer classes, a default elasticity of 1 only for residential and commercial load (ASSUMPTION), and a visible note in the result.
- **DC flow has no voltage.** A fix may fail on voltage. Mitigation: the warning in every proposal and the `uncertain` flag of the engine.
- **Data for siting is missing (G6).** Without it the "add a plant" remedy is a guess. Mitigation: start with the remedies that need no new data (redispatch, upgrade a line, storage), and add siting once a source is chosen.
- **Hallucination.** The agent states numbers it did not get from a tool. Mitigation: grounding, the question set, and tests that fail on an unreferenced number.
- **Two engine versions** (`docs/escenarios.md` section 6). A comparison against a stale base case is wrong. Mitigation: P0 regenerates the base with a decision.
- **Scope.** This is large. P1 alone is already a useful product; the plan is ordered so each phase can stand.

## 10. Open decisions for the team (ask, do not assume)

1. **Order.** P1 (table panel) before the agent, as proposed, or the agent chat first?
2. **Who edits lines.** Confirm the rule of section 2.2: injections are edited freely; cable changes are proposals approved by a person.
3. **What is "good health".** Confirm or change the items and thresholds of 5.3 step 2.
4. **Consumer classes.** Does the data have them? If not, accept the assumption that only residential and commercial load follows population.
5. **Siting and cost sources.** Which official datasets for river flows, solar and wind resource, protected areas and costs? (PyPSA-CL `Costs.xlsx` is already in the pipeline.)
6. **2050 scenarios.** Which official scenario defines the numbers: the long-term energy planning of the Ministerio de Energía, or the team's own?
7. **Where drafts live.** In memory per session (as the theatre runs) or in S3 (issue #34) so they survive a restart and can be shared?
8. **LLM.** Which provider, and is it available in the deploy (`CASCADASEN_LLM_ENABLED`, AWS permissions)? Without it, only P1 ships.
9. **Relation to the theatre.** Should the theatre agents be able to use drafts (for example "what if this plant is lost for a week")? Proposed: not in 2.0.
10. **Guardrails.** Confirm the reading of `cyber.md` section 8 for this agent: N-1 screening is reported by effect, with no ranking of attack targets.
