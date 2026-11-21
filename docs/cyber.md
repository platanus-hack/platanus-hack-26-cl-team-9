# Simulation objective: consequences of cyberattacks on the SEN

Last updated: 2026-11-21. Requested by Ricardo on 2026-11-21; the rest of the team still has to confirm it (`plan.md` section 9, item 10). Read after `idea.md`. Numbers in brackets refer to `datasets.md` section 7.

## 1. Objective

The main objective of the simulation is to **estimate the consequences of a cyberattack on the Chilean national grid (SEN)**: which zones lose power, how many people, for how long, at what cost, and which defence would have contained it. The same engine also covers accidental failures like 25F. Cyberattacks are the main threat the scenarios are built around.

The simulator works from consequences and does not depend on the cause:

- **Input:** the physical effect of the attack on the grid. That means which elements disconnect, which defences fail, which control is lost, and at what time and operating point.
- **Output:** the physical, social and economic consequence, and what would have contained it.
- **Not modelled:** how the attack is carried out (intrusion path, malware, vulnerabilities, products, vendors). The grid reacts the same way to a breaker opened by an attacker and to one opened by a protection relay. Because the physics is the same, the model validated in `plan.md` section 5 applies to cyber scenarios.

This follows the premise of Consequence-driven Cyber-informed Engineering (CCE), a method from Idaho National Laboratory [38]. CCE assumes that a skilled and determined adversary can get into the control systems. The effort then goes into finding the outcomes with the worst consequences and the engineering measures that limit them, not into auditing the IT.

Pitch line (Spanish, UI tone): "Si un ciberataque logra desconectar esto, ¿cuánta gente queda sin luz, por cuánto tiempo, y qué lo habría evitado?"

## 2. Why cyberattacks are the main threat to model

1. **It has already happened in the SEN.** On 27 Aug 2026 at 13:10 the CEN registered the forced disconnection of the Huatacondo solar plant (103 MW, Tarapacá) and its battery system (98 MW / 312 MWh, still in commissioning). The declared cause was a "cyberattack on the Huatacondo facilities". Both still had 0% availability in the CEN daily report of 14 Nov 2026 [34][35]. On the same day a 220/23 kV transformer at the Santa Rita substation was disconnected, also citing a cyberattack. That evening two thermal plants in Los Vilos (Coquimbo) were declared unavailable for dispatch after losing monitoring and remote control. Whether these events are related has not been established [34]. No loss of customer supply was reported, and no technical findings have been published [35]. CEN daily reports record the cause each operator declares; they are not investigations [34]. pv magazine reviewed 360 of the 365 daily reports from Oct 2025 to Oct 2026 and found no other incident explicitly attributed to a cyberattack [34].
2. **25F shows what a single intervention on a protection system can do.** The 25F initiating event was an unauthorised intervention on a protection device [3]. It was not a cyberattack, but remote manipulation of protection or control equipment would have the same physical effect. Once the 500 kV line was lost, the whole country depended on every defence working (`idea.md` section 5).
3. **Cyberattacks have caused blackouts elsewhere.** In Ukraine in December 2015, breakers were opened remotely at distribution substations. About 225,000 customers lost power for up to several hours. In December 2016 a transmission substation near Kyiv was disconnected for about an hour, which cut about one fifth of the city's consumption at that time [39]. These figures come from secondary sources, vary between them and were not verified in this project.
4. **Regulation now requires it.** Ley 21.663, the Framework Cybersecurity Law, covers essential services. The national agency (ANCI) designates operators of vital importance (OIV), which must keep operational continuity and cybersecurity plans. An incident with potentially significant impact must be notified within 3 hours, updated within 72 hours, and closed with a final report within 15 days [35][36]. On 28 Aug 2026 the CNE opened public consultation on a draft cybersecurity technical standard for the electricity sector [37]. A continuity plan needs a consequence estimate, and none is public for the SEN today.

### What makes an attack different from a random failure

These differences define what the simulation must be able to represent.

| Property | Random failure (what N-1 studies assume) | Cyberattack | What the model must do |
|---|---|---|---|
| Simultaneity | One element at a time | Many elements at the same moment when they share a control system, a remote-access platform or a vendor (common mode) | Allow the simultaneous loss of a group of plants (by zone and technology), beyond the 1-3 element limit |
| Defences | Assumed to work, or to fail at random | Can be disabled or delayed as part of the attack | Every defence (load-shedding steps, north defence scheme, ride-through) can be switched off per scenario |
| Timing | Any moment | Can be chosen: low inertia (midday with lots of solar), high transfer on the north corridor | Run each scenario at several operating points and report the worst one |
| Duration | Repair time, usually hours | Recovery can take months (Huatacondo was still offline after about 80 days), with manual operation | Duration is an explicit, editable input. Restoration is not modelled |
| Observability | Operators see and control the grid | Operators can lose monitoring and remote control | Loss of control is modelled as plants that are unavailable for dispatch and reserve |

## 3. Questions the simulation must answer

Each scenario answers these questions in this order.

| # | Question | Output | Engine piece | Priority |
|---|---|---|---|---|
| Q1 | Does the grid absorb it? | Consequence level (section 5), islands formed, minimum frequency per island | Cascade and island frequency model (`stack.md` 4.3-4.4) | P0 |
| Q2 | Who loses power? | People without power per comuna and node; MW of load shed | Population per substation (`datasets.md` section 0) | P0 |
| Q3 | For how long, and at what cost? | Unserved energy (MWh) = load lost x duration; cost at the CNE failure cost of 8.79 US$/kWh [19] | Duration as an editable assumption | P1 |
| Q4 | Which critical services are affected? | Hospitals, water, Metro left without power | Needs a critical-load dataset (missing, section 9) | P2 |
| Q5 | How close was it to something worse? | Margin: extra MW of simultaneous loss before the consequence level goes up | Parameter sweep on the scenario size | P1 |
| Q6 | What would have contained it? | Minimum fast-battery MW per island, load-shedding setting, defence scheme kept active, ride-through threshold | `stack.md` 4.5; defence optimiser (`idea.md` section 6, item 6) | P1 |

No PDF answers Q5 or Q6. They are the main "new question" content (`plan.md` phase 8).

## 4. Scenario classes (defined by effect)

Each scenario is defined by its effect on the grid. The scenario name mentions the cyberattack as its motivation. The events on screen describe what the grid lost.

| Class | Effect on the grid | Public reference | Engine input | Status |
|---|---|---|---|---|
| C1 Generation loss | One or more plants disconnect at t = 0 | Huatacondo, 103 MW [34] | `plant_trip` events; existing `elements_out` | P0 (the engine already plans single plants) |
| C2 Common-mode generation loss | A share of the plants of one technology in one zone disconnect at once (shared control platform or inverter fleet) | No Chilean case. The CEN 2026 load-shedding study covers a sudden 3,000 MW loss [14] | New `group_out` input: zone, technology, share | P1; needs the contract change in `stack.md` 6.1 |
| C3 Transmission opening | Breakers open on a line or at a substation | Ukraine 2015/2016 [39]; Santa Rita transformer [34] | `line_cut`; node out of service | P0 |
| C4 Defence disabled or delayed | A load-shedding step, the north defence scheme (PDCE-ZN) or automatic generation shedding does not act, or acts late | 25F: about 1,971 MW of centre-south generation disconnected when it should have ridden through [4]. Comparing the "as it happened" and "per grid code" modes is already a C4 experiment | Defence mode plus a `defenses_disabled` list | P1 |
| C5 Loss of monitoring and control | Plants stay online but cannot be dispatched and give no reserve | Olivos and Espinos, 27 Aug 2026 [34] | Lower available reserve in the island | P1 |
| C6 Combined | C1, C2 or C3 plus C4, at an adverse operating point | The CCE "assume compromise" case | Combination of the above | P1; demo candidate |

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

## 7. Validation of cyber scenarios

Cyber scenarios reuse the physics validated by V1-V8 (`plan.md` section 5). Two cases are specific to them:

- **V7** [14] (loss of 3,000 MW of synchronous generation in low-demand 2026; the system holds) is the design-basis large simultaneous loss. In that operating point, any C2 scenario of that size or smaller must give L0 or L1. It is the anchor for the margin question Q5.
- **V10** (new, weak consistency check): losing 103 MW in Norte Grande at midday, equivalent to Huatacondo, must give L0 or L1 with no island collapsing, because no supply loss was reported [34][35]. The check is weak for three reasons: the absence of reported outages is not a measurement, the plant's output at 13:10 is unknown, and the disconnection was requested by a control centre, so it was not necessarily a sudden trip.

There is no public measurement of a cyberattack's consequence on the SEN to test the model against. The screen must say so: cyber scenarios are "consequence estimates", not validated predictions.

## 8. Guardrails (dual use)

The tool exists for prevention and must not become an attack planner. These rules extend `idea.md` section 8 and replace nothing in it.

1. **No attack technique.** Code, data, docs and UI contain no intrusion paths, malware, vulnerabilities, protocols, products, vendors, or links between plants and control centres.
2. **No search for the worst attack.** No optimiser or ranking looks for the elements whose compromise causes the most damage ("minimum cut"). Sweeps such as N-2 (`idea.md` section 6, item 4) are used only for validation against classifications the CEN already publishes [5]. They are shown aggregated by zone, never as a ranked list. The optimiser searches over defences, never over attacks.
3. **Zone-level resolution** for group scenarios (C2, C6). Company names never appear on screen (`stack.md` section 9).
4. **Public references only.** Scenarios cite public cases: the Huatacondo reports, 25F and CEN studies. Do not collect non-public information about the incident.
5. Every cyber scenario shows the notice: "Escenario hipotético: se modela el efecto, no el ataque."
6. Narration describes effects and prevention ("se desconectan 400 MW solares en el Norte Grande"), never attack steps.

## 9. Data gaps

| Need | Status | Fallback |
|---|---|---|
| Critical loads (hospitals, water, Metro) with location | Missing. Public registries of health facilities may exist; not checked | P2; Q4 stays empty |
| Outage duration after cyberattacks | Missing for Chile. Ukraine: about 1 to several hours [39]. Huatacondo: plant offline for about 3 months, but no customer outage | Editable input. The team chooses the default, labelled "assumption" |
| Ride-through settings per technology | Missing; synthetic values proposed in `idea.md` section 6, item 1 | Assumption |
| Which plants share control systems | Do not collect (guardrail 1) | Groups by zone and technology |
| Energy-vulnerable households | Mapa de Vulnerabilidad Energetica [33] found, not used | P2 |

## 10. Use in the demo

Proposed segment (about 30 s) after the 25F replica, replacing or extending step 4 of the 2-minute script (`idea.md` section 3.3):

1. "Agosto 2026: un ciberataque sacó de servicio una planta solar de 103 MW en Tarapacá. La red lo absorbió." The simulator shows L0.
2. "¿Y si el mismo efecto alcanza al 40% de la generación solar del norte a mediodía, con el esquema de defensa desactivado?" The C6 scenario runs, and the level and counter go up.
3. "¿Qué lo habría evitado?" The panel shows MW of fast batteries, or the defence that has to stay active.

Numbers in this segment are placeholders until the engine computes them. Fixtures must carry the "fixture" label.
