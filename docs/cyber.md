# Resilience scenarios: grid consequences of cyber-related disturbances

Last updated: 2026-11-21. Requested by Ricardo on 2026-11-21; the rest of the team still has to confirm it (`plan.md` section 9, item 10). Read after `idea.md`. Numbers in brackets refer to `datasets.md` section 7.

**Context.** Sub50 (formerly CascadaSEN) is a hackathon project for the simulation track. It is an educational, preventive tool: a power-flow and frequency simulator that shows how the Chilean grid (SEN) responds when some elements go out of service, and which defences keep a local event from becoming a blackout. This document covers one family of scenarios: disturbances motivated by public cyber incidents. The simulator only takes grid-level effects as input (an element out of service, a defence not acting). It contains no information about how anyone could cause those effects, and it is not meant to find real weak points. Section 8 lists the guardrails that keep it that way.

The strategic experimentation layer built on top of this engine (agents, observed vs real state, adaptive adversary, campaigns) is described in `strategy.md`; read it after this document.

## 1. Objective

The main objective of the simulation is to **estimate the grid consequences of a disturbance like the ones public cyber incidents have caused**: which zones lose power, how many people, for how long, at what cost, and which defence would have contained it. The same engine also covers accidental failures like 25F. Cyber incidents are the motivating context the scenarios are built around, because they are the case current regulation asks operators to plan for (section 2).

The simulator works from consequences and does not depend on the cause:

- **Input:** a physical effect on the grid that the user picks: which elements disconnect, which defences do not act, which plants cannot be dispatched, and at what time and operating point.
- **Output:** the physical, social and economic consequence, and what would have contained it.
- **Out of scope:** any cause-side detail (intrusion path, malware, vulnerabilities, protocols, products, vendors). The grid responds the same way to a breaker opened by mistake, by a protection relay or by unauthorised access. Because the physics is the same, the model validated in `plan.md` section 5 applies to these scenarios.

This follows Consequence-driven Cyber-informed Engineering (CCE), a resilience method from Idaho National Laboratory [38]. CCE puts the effort into understanding consequences and the engineering measures that limit them, instead of auditing IT systems.

Pitch line (Spanish, UI tone): "Si un incidente deja fuera de servicio esto, ¿cuánta gente queda sin luz, por cuánto tiempo, y qué lo habría evitado?"

## 2. Why this scenario family matters

1. **There is a recent public case in the SEN.** On 27 Aug 2026 at 13:10 the CEN registered the forced disconnection of the Huatacondo solar plant (103 MW, Tarapacá) and its battery system (98 MW / 312 MWh, still in commissioning). The declared cause was a "cyberattack on the Huatacondo facilities". Both still had 0% availability in the CEN daily report of 14 Nov 2026 [34][35]. On the same day a 220/23 kV transformer at the Santa Rita substation was disconnected, also with that declared cause. That evening two thermal plants in Los Vilos (Coquimbo) were declared unavailable for dispatch after losing monitoring and remote control. Whether these events are related has not been established [34]. No loss of customer supply was reported, and no technical findings have been published [35]. CEN daily reports record the cause each operator declares; they are not investigations [34]. pv magazine reviewed 360 of the 365 daily reports from Oct 2025 to Oct 2026 and found no other incident explicitly attributed to a cyberattack [34].
2. **25F shows what one event on a protection system can do.** The 25F initiating event was an unauthorised intervention on a protection device [3]. It was not a cyber incident, but the physical effect on the grid is the kind of input this family covers. Once the 500 kV line was lost, the whole country depended on every defence working (`idea.md` section 5).
3. **Public incidents abroad caused outages.** Public reports on Ukraine describe distribution substations disconnected in December 2015 (about 225,000 customers without power for up to several hours) and a transmission substation near Kyiv disconnected in December 2016 for about an hour (about one fifth of the city's consumption at that time) [39]. These figures come from secondary sources, vary between them and were not verified in this project. They are used only as an order of magnitude for outage duration.
4. **Regulation now requires consequence estimates.** Ley 21.663, the Framework Cybersecurity Law, covers essential services. The national agency (ANCI) designates operators of vital importance (OIV), which must keep operational continuity and cybersecurity plans. An incident with potentially significant impact must be notified within 3 hours, updated within 72 hours, and closed with a final report within 15 days [35][36]. On 28 Aug 2026 the CNE opened public consultation on a draft cybersecurity technical standard for the electricity sector [37]. A continuity plan needs a consequence estimate, and none is public for the SEN today.

### What a resilience study must represent beyond classic N-1

Classic N-1 studies assume one random failure at a time with all defences working. Continuity planning asks broader questions. These are the model capabilities that follow, all expressed as grid-level inputs.

| Property | Classic N-1 assumption | Broader continuity question | What the model must do |
|---|---|---|---|
| Simultaneity | One element at a time | Several elements out at once (common-mode loss, as in the CEN 3,000 MW study [14]) | Allow the simultaneous loss of a group of plants, by zone and technology, beyond the 1-3 element limit |
| Defences | Assumed to work, or to fail at random | What if a defence does not act, or acts late? | Every defence (load-shedding steps, north defence scheme, ride-through) can be switched off per scenario, to measure how much each one contributes |
| Operating point | Any moment | Results depend strongly on inertia and transfers (for example midday with lots of solar) | Run each scenario at several standard operating points and show the most demanding one, as a stress test |
| Duration | Repair time, usually hours | Recovery can take much longer (Huatacondo was still offline after about 80 days) | Duration is an explicit, editable input. Restoration is not modelled |
| Observability | Operators see and control the grid | A plant may stay online without remote dispatch | Modelled as plants unavailable for dispatch and reserve |

## 3. Questions the simulation must answer

Each scenario answers these questions in this order.

| # | Question | Output | Engine piece | Priority |
|---|---|---|---|---|
| Q1 | Does the grid absorb it? | Consequence level (section 5), islands formed, minimum frequency per island | Cascade and island frequency model (`stack.md` 4.3-4.4) | P0 |
| Q2 | Who loses power? | People without power per comuna and node; MW of load shed | Population per substation (`datasets.md` section 0) | P0 |
| Q3 | For how long, and at what cost? | Unserved energy (MWh) = load lost x duration; cost at the CNE failure cost of 8.79 US$/kWh [19] | Duration as an editable assumption | P1 |
| Q4 | Which critical services are affected? | Hospitals, water, Metro left without power | Needs a critical-load dataset (missing, section 9) | P2 |
| Q5 | How much margin is left? | Extra MW of simultaneous loss the grid absorbs before the consequence level goes up | Parameter sweep on the scenario size | P1 |
| Q6 | What would have contained it? | Minimum fast-battery MW per island, load-shedding setting, defence scheme kept active, ride-through threshold | `stack.md` 4.5; defence optimiser (`idea.md` section 6, item 6) | P1 |

No PDF answers Q5 or Q6. They are the main "new question" content (`plan.md` phase 8).

## 4. Scenario classes (defined by effect)

Each scenario is defined only by its effect on the grid. The scenario name may cite the public incident that motivates it. The events on screen describe what the grid lost.

| Class | Effect on the grid | Public reference | Engine input | Status |
|---|---|---|---|---|
| C1 Generation loss | One or more plants disconnect at t = 0 | Huatacondo, 103 MW [34] | `plant_trip` events; existing `elements_out` | P0 (the engine already plans single plants) |
| C2 Common-mode generation loss | A share of the plants of one technology in one zone disconnect at once | No Chilean case. The CEN 2026 load-shedding study covers a sudden 3,000 MW loss [14] | New `group_out` input: zone, technology, share | P1; needs the contract change in `stack.md` 6.1 |
| C3 Transmission opening | A line or a substation goes out of service | Ukraine 2015/2016 [39]; Santa Rita transformer [34] | `line_cut`; node out of service | P0 |
| C4 Defence not acting | A load-shedding step, the north defence scheme (PDCE-ZN) or automatic generation shedding does not act, or acts late | 25F: about 1,971 MW of centre-south generation disconnected when it should have ridden through [4]. Comparing the "as it happened" and "per grid code" modes is already a C4 experiment | Defence mode plus a `defenses_disabled` list | P1 |
| C5 Loss of remote dispatch | Plants stay online but cannot be dispatched and give no reserve | Olivos and Espinos, 27 Aug 2026 [34] | Lower available reserve in the island | P1 |
| C6 Combined stress test | C1, C2 or C3 plus C4, at a demanding standard operating point | CCE-style stress test [38] | Combination of the above | P1; demo candidate |

Rule: C2 and C6 are expressed at zone and technology level (for example "40% of the solar in Norte Grande"), never as a list of named plants or companies.

## 5. Consequence levels

| Level | Name | Definition | Island results (`stack.md` 4.6) |
|---|---|---|---|
| L0 | Absorbed | No island collapses and no load is shed | All "Maintains"; `load_shed_mw` = 0 |
| L1 | Contained | Automatic load shedding acts; every island survives | All "Maintains"; `load_shed_mw` > 0 |
| L2 | Regional blackout | At least one island collapses, but not all of them | Some "Blackout" |
| L3 | National blackout | Every island of the SEN collapses (as on 25F) | All "Blackout" |

If any island is "Uncertain" or "Not modelled", the level carries an "uncertain" badge.

The **consequence card** (headline panel) shows: the level, people without power, MW shed, unserved MWh and cost for the chosen duration, critical loads (once the data exists), and what would have contained the event.

## 6. Contract and engine changes (proposal)

Details are in `stack.md` section 6.1 and the API table in section 7. In short: an optional `cause` block and consequence metrics in `timeline.json`, two new event types (`defense_disabled`, `control_lost`), and three new API fields (`group_out`, `defenses_disabled`, `outage_duration_h`). All of them are optional, so the MVP fixtures stay valid.

## 7. Validation of these scenarios

These scenarios reuse the physics validated by V1-V8 (`plan.md` section 5). Two cases are specific to them:

- **V7** [14] (loss of 3,000 MW of synchronous generation in low-demand 2026; the system holds) is the design-basis large simultaneous loss. In that operating point, any C2 scenario of that size or smaller must give L0 or L1. It is the anchor for the margin question Q5.
- **V10** (new, weak consistency check): losing 103 MW in Norte Grande at midday, equivalent to Huatacondo, must give L0 or L1 with no island collapsing, because no supply loss was reported [34][35]. The check is weak for three reasons: the absence of reported outages is not a measurement, the plant's output at 13:10 is unknown, and the disconnection was requested by a control centre, so it was not necessarily a sudden trip.

There is no public measurement of the consequence of a cyber incident on the SEN to test the model against. The screen must say so: these scenarios are "consequence estimates" for a hypothetical case, not validated predictions.

## 8. Guardrails (dual use)

The tool exists for prevention and education. It must stay a consequence and defence simulator and must never become a tool for finding real weak points. These rules extend `idea.md` section 8 and replace nothing in it.

1. **Effects only, no technique.** Code, data, docs and UI contain no intrusion paths, malware, vulnerabilities, protocols, products, vendors, or links between plants and control centres.
2. **No weak-point search.** No optimiser or ranking looks for the elements whose loss causes the most damage ("minimum cut"). Sweeps such as N-2 (`idea.md` section 6, item 4) are used only for validation against classifications the CEN already publishes [5]. They are shown aggregated by zone, never as a ranked list. The optimiser searches over defences, never over contingencies. The adaptive adversary of the strategic layer (item 7) is not an exception: it adapts inside an abstract catalog, and its results are reported as defensive-policy outcomes, never as a ranking of elements or zones.
3. **Zone-level resolution** for group scenarios (C2, C6). Company names never appear on screen (`stack.md` section 9).
4. **Public references only.** Scenarios cite public cases: the Huatacondo reports, 25F and CEN studies. Do not collect non-public information about any incident.
5. Every scenario of this family shows the notice: "Escenario hipotético: se modela el efecto, no el ataque."
6. Narration describes effects and prevention ("se desconectan 400 MW solares en el Norte Grande"), never how they could be caused.
7. **Adaptive adversary (strategic layer, `strategy.md`; pending team confirmation).** The experimentation layer includes an adversary agent that adapts its strategy when the defence changes. It may only:
   - trigger events from the abstract catalog in `strategy.md` section 6 (grid-level effects C1-C5, and digital effects such as telemetry loss, delayed or unreliable data, communications loss and false alarms), always at operating-area or function level;
   - pursue objectives that target the defender's decision quality: observability, uncertainty, resources, unnecessary decisions, recovery;
   - see only what the defence exposes.

   It has no technique, no real vulnerability and no real system model behind it. Campaign outputs compare defensive policies and capabilities. They never list which elements or areas hurt the most. The adversary is seeded code (reproducible from the run seed); an LLM never plays it. Its reward measures its abstract objective (persistence, defensive posture, delayed recovery), never megawatts or people.

## 9. Data gaps

| Need | Status | Fallback |
|---|---|---|
| Critical loads (hospitals, water, Metro) with location | Missing. Public registries of health facilities may exist; not checked | P2; Q4 stays empty |
| Outage duration after cyber incidents | Missing for Chile. Ukraine: about 1 to several hours [39]. Huatacondo: plant offline for about 3 months, but no customer outage | Editable input. The team chooses the default, labelled "assumption" |
| Ride-through settings per technology | Missing; synthetic values proposed in `idea.md` section 6, item 1 | Assumption |
| Which plants share control systems | Out of scope; do not collect (guardrail 1) | Groups by zone and technology |
| Energy-vulnerable households | Mapa de Vulnerabilidad Energetica [33] found, not used | P2 |

## 10. Use in the demo

Proposed segment (about 30 s) after the 25F replica, replacing or extending step 4 of the 2-minute script (`idea.md` section 3.3):

1. "Agosto 2026: un incidente de ciberseguridad sacó de servicio una planta solar de 103 MW en Tarapacá. La red lo absorbió." The simulator shows L0.
2. "¿Y si una pérdida simultánea alcanza al 40% de la generación solar del norte a mediodía, y el esquema de defensa no actúa?" The C6 stress test runs, and the level and counter go up.
3. "¿Qué lo habría evitado?" The panel shows MW of fast batteries, or the defence that has to stay active.

Numbers in this segment are placeholders until the engine computes them. Fixtures must carry the "fixture" label.
