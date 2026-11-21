# Strategic experimentation layer: keeping a mission under adverse conditions

Last updated: 2026-11-21. Requested by Ricardo on 2026-11-21; **pending team confirmation** (`plan.md` section 9, items 4 and 10). Read after `cyber.md`. This document describes what the backend simulates on top of the physical engine (`stack.md` section 4) and why. The HTTP contract is in `stack.md` section 7.1.

## 1. Thesis and object of analysis

The largest risk to critical infrastructure is not always that a component fails. It is that the organisation loses the ability to understand what is happening and to coordinate a response before the problem exceeds its capacity to control it.

So the object of analysis is not an attack or a failure. It is the **ability of an electric utility to keep its essential mission under adverse conditions**:

- keep supply within safe conditions;
- keep supervision and control capability;
- protect priority loads;
- stop a contingency from spreading;
- keep the capacity to respond while losing resources;
- recover operation safely.

The infrastructure is the means. Continuity of service is the mission. Agents are the decision makers. The environment is where the competition happens.

The framework applies General Staff rigour to a civil problem (mission, operational environment, centre of gravity, dependencies, uncertainty, adversary, freedom of action, reserves, decision, adaptation, after-action review). It does not imitate any real military operation. It uses the four cyber-resilience goals of NIST engineering guidance (anticipate, withstand, recover, adapt) as the frame for what is measured.

Guiding question: **"¿Qué tan buena es nuestra estrategia de defensa cuando el escenario deja de comportarse como esperábamos?"**

Primary user (decided 2026-11-21): the operations, continuity and cybersecurity teams of an electric utility. Main advantage: testing defensive policies against an adaptive adversary (Mode II, section 7). Diagnosis (Mode I) and capability planning (Mode III) come out as variants of the same campaign runner.

## 2. The theatre: five interacting systems

| System | Contents | Implemented in |
|---|---|---|
| Physical environment | Generation, transmission, load, island frequency, defences | `backend/src/cascadasen/domain/simulation/` |
| Digital environment | Supervision, telemetry, communications, data integrity, remote control | `domain/theater/digital.py` |
| Adversarial force | One agent with an abstract objective that adapts | `domain/agents/adversary.py` |
| Defensive force | Agents that detect, decide, coordinate, contain and recover | `domain/agents/` |
| Temporal and operational environment | Time, uncertainty, resources, constraints, external events, consequences | `domain/theater/` |

They are not run independently. A digital event degrades what supervision shows; ISR cannot tell whether it is a failure or an intentional action; the commander decides with that uncertainty; the physical engine computes which operating constraints exist.

### 2.1 Network: 13 operating areas

The theatre runs on a reduced trunk network built from the real SEN snapshot (`data/processed/grid_snapshot.json`). Each **operating area** aggregates every main-grid node inside a latitude band. Aysén (SEA) and Magallanes (SEM) are separate systems and are left out. Corridors join areas; parallel 500 kV and lower-voltage lines stay as separate corridors (`stack.md` section 4.1). The bands are in `domain/simulation/params/network.yaml`.

| Area | Name | Band (lat) | Anchors |
|---|---|---|---|
| A01 | Arica–Iquique | north of -21.3 | Parinacota, Cóndores, Tarapacá |
| A02 | Crucero–Kimal | -21.3 to -22.7 | Crucero, Encuentro, Kimal |
| A03 | Antofagasta–Taltal | -22.7 to -25.6 | Mejillones, Los Changos, Jadresic |
| A04 | Cumbre–Diego de Almagro | -25.6 to -26.9 | Cumbre |
| A05 | Copiapó | -26.9 to -28.0 | Cardones, Nueva Cardones |
| A06 | Vallenar | -28.0 to -29.3 | Maitencillo, Nueva Maitencillo |
| A07 | La Serena–Coquimbo | -29.3 to -31.3 | Pan de Azúcar, Nueva Pan de Azúcar |
| A08 | Los Vilos–Valparaíso | -31.3 to -33.3 | Los Vilos, Quillota, Polpaico |
| A09 | Santiago | -33.3 to -33.9 | Lo Aguirre, Cerro Navia, Alto Jahuel |
| A10 | O'Higgins–Maule | -33.9 to -36.4 | Rapel, Itahue, Ancoa |
| A11 | Biobío | -36.4 to -38.2 | Charrúa, Entre Ríos, Hualpén, Mulchén |
| A12 | Araucanía | -38.2 to -39.7 | Temuco, Ciruelos |
| A13 | Los Ríos–Los Lagos | south of -39.7 | Valdivia, Pichirropulli, Puerto Montt |

The A06–A07 boundary separates Nueva Maitencillo from Nueva Pan de Azúcar: the 25F corridor (V2). Each area lists the real node ids it covers (`aggregates`), so the frontend can map a click on any substation to its area. Demand per area, dispatch and inertia come from operating points in `params/operating_points.yaml`; every value there carries a source or `is_assumption: true`.

## 3. Three states

| State | What it is | Who sees it |
|---|---|---|
| Real | What is happening: physical grid plus true digital health | The engine, the validator and the evaluator. Never an agent |
| Observed | What supervision shows: real state passed through the digital engine (missing, stale or unreliable values, false alarms) | Agents, filtered by role |
| Estimated | What each agent believes, built only from its own feed and memory | That agent |

The distance between the three states is a product variable. It is measured every cycle (section 8). Unreliable data is the hardest case: a value that looks normal but is wrong. SCADA does not flag it.

## 4. Two clocks

- **Operational cycle:** 5 minutes per cycle (assumption), 24 to 36 cycles per run. Decisions, digital degradation, resource use and recovery happen per cycle.
- **Physical transient:** inside a cycle, any physical event or switching action runs the cascade and a 20 s island-frequency transient (`stack.md` sections 4.3 and 4.4). The resulting quasi-steady state holds until the next change.

Restoration in the theatre is an operational abstraction: an area recovers a share of its load per cycle while crews and control are available (parameters flagged `is_assumption`). It is not an electrical restoration model; `cyber.md` section 2 still applies to the physics.

## 5. Agents

Every agent has its own mission, limited information, a set of capabilities, limited resources, decision rules, memory, success criteria, and permissions. Each holds a different representation of the state of the infrastructure.

| Agent | Mission | Sees | Can do | Cannot do |
|---|---|---|---|---|
| C2 Commander | Set priorities and intent, allocate resources, resolve conflicts | ISR picture, proposals, resource summary | Approve or reject courses of action (COAs) | Bypass the validator or physical limits |
| ISR | Build the operational picture from incomplete evidence | Observed state, alarms, field reports | Task extra monitoring, request field checks | Act on the grid |
| Operations | Propose and coordinate defensive measures | ISR picture, intent | Propose operational COAs | Order actions outside its permissions |
| Stabilisation | Protect physical constraints, prioritise continuity and safe recovery | Observed physical state | Propose stabilising COAs, veto unsafe ones (checked on its own estimate, not on the real grid) | See the real grid |
| Logistics | Manage reserves, redundancy and contingency resources | Resource ledger | Reserve and release resources, request external support | Spend resources above the intent caps |
| Auditor | Record evidence, find coordination errors, check that constraints held | Everything, after each cycle, read-only | Report findings | Change the state or the log |
| Adversary | Pursue one abstract objective with a limited budget | Only what the defence exposes | Trigger events from the abstract catalog | Use anything outside the catalog |

### 5.1 Adaptive adversary

- **Objective:** one abstract objective: reduce observability, raise uncertainty, pressure defensive resources, provoke unnecessary defensive decisions, or complicate recovery.
- **Means:** a limited budget and opportunities (cooldown between actions), and only the abstract event catalog (section 6).
- **Information:** it sees only signals the defence exposes (areas switched to manual operation or segmented, effects cleared, public blackouts) and keeps its own estimate of the defensive posture.
- **Adaptation:** seeded multiplicative weights (EXP3) over event type × area, rewarded by an observable proxy of its objective. It changes strategy when the defence changes.
- **Static variant:** the same budget following the scripted sequence of the template. Comparing the two gives the Adaptation Index.
- Deterministic code, no LLM.

## 6. Events and defensive actions

All events are abstract and defined at area or function level (`cyber.md` section 8).

| Family | Events |
|---|---|
| Physical (`cyber.md` section 4) | C1 generation loss, C2 common-mode loss (zone and technology), C3 transmission opening, C4 defence not acting, C5 loss of remote dispatch |
| Digital | D1 telemetry loss, D2 telemetry delay, D3 unreliable data, D4 communications loss, D5 false alarms, D6 loss of an external support service |
| External | E1 demand surge, E2 renewable drop |

Defensive COAs: ISR tasking, field verification, manual/local operation, backup communications, digital segmentation, preventive load reduction, fast reserve, battery support, re-arm a defence, controlled islanding, restore element, request external support. Each COA states its cost, expected effect, risk, required resources, reversibility, and which roles may propose or approve it. Resources: field crews, backup communications kits, fast reserve MW, battery MW, analyst attention and operator attention per cycle (which models saturation).

## 7. Strategic cycle, validator and audit

Each operational cycle runs six steps:

1. **Understand.** Each agent updates its estimate from its partial feed. ISR keeps hypotheses: failure vs intentional, affected areas, confidence.
2. **Intent.** C2 sets what must be protected, the acceptable risk and the resource caps.
3. **Plan.** Operations, Stabilisation and Logistics propose COAs with cost, benefit, risk and requirements.
4. **Validate and decide.** A deterministic validator checks permissions, authority, resources, physical feasibility, mission constraints and side effects. C2 chooses among the valid COAs within its attention capacity.
5. **Execute and observe.** The engine applies the decisions plus scheduled, injected and adversary events to the real state. Agents receive only what they could observe.
6. **Evaluate and adapt.** The Auditor scores the cycle. Agents update hypotheses, plans and priorities. The adversary updates its weights.

Inviolable rules: Operations cannot order arbitrary actions, the commander cannot skip physical constraints, and the Auditor cannot change the outcome. The audit log is append-only and hash-chained. A run is fully reproducible from its recipe: configuration, seed, and injected events with their cycle.

Policies under test (parameters over C2, ISR and Operations):

- **A Reactive:** acts once an anomaly is confirmed (ISR confidence ≥ 0.8). Avoids hasty decisions, may react late.
- **B Preventive:** acts on the first sign of degradation (≥ 0.3) with conservative measures. Reduces exposure, consumes resources, has side effects.
- **C Adaptive coordination:** verifies first, prefers cheap reversible measures, escalates as confidence grows, and keeps a resource reserve to preserve options.

Modes:

- **I Diagnosis:** scenarios without an adaptive adversary. Finds where continuity is lost, aggregated by area.
- **II Adversarial experimentation:** policies against the adaptive and the static adversary at several uncertainty levels.
- **III Capability planning:** the same scenarios with capability variants (observability coverage, comms redundancy, crews, battery MW). It estimates how outcomes change; it does not claim an investment prevents incidents.

## 8. Indicators

All indicators are **experimental proposals, not standards**. Outputs label them `experimental: true`. Notation: cycle `k`, horizon `K`, demand `D_k` and served load `S_k` in MW, priority areas `P`.

| Indicator | Question | Definition |
|---|---|---|
| Mission continuity (MC) | What share of essential service was kept? | `Σ_k S_k / Σ_k D_k`; also restricted to `P` |
| Situational awareness | How long until the organisation understood the incident? | Time to understanding (TTU): cycles from onset until ISR's leading cause is correct with p ≥ 0.7 and its affected areas match the real ones with Jaccard ≥ 0.8. Also the estimation gap `G_k = mean over areas of |S_real − S_estimated(C2)| / D_area` |
| Response capacity | How many defensive actions were executed correctly? | executed and effective COAs / proposed COAs |
| Resistance | How much damage was contained without losing the mission? | largest load loss (MW) while MC stayed above the mission threshold |
| Operational reserve | What resources were left? | mean of remaining/initial per resource pool, at the end and the minimum over the run |
| Recoverability | How long until essential capability was back? | cycles from onset until `S_k ≥ 0.99 D_k` and observability ≥ 0.9 |
| Coordination effectiveness | How many conflicts, delays and contradictions? | counts of conflicting proposals, detection-to-decision delay (cycles), and decisions reversed within 2 cycles |
| Wrong decisions | — | COAs executed in areas with no real effect (for example segmenting an area that only had false alarms) |

Three proposed indices:

- **A. Freedom of Action Index:** `FAI_k = |safe and viable COAs at k| / |safe and viable COAs at the first cycle|`. The evaluator runs the validator on the whole catalog against the real state. Agents never see this.
- **B. Decisional Fragility Index:** `DFI = (MC_perfect − MC_degraded) / MC_perfect`, from paired runs with the same seed, policy and events at uncertainty 0 and at the tested level. 0 means information quality did not matter.
- **C. Adaptation Index:** `AI = MC_vs_adaptive / MC_vs_static` for one policy on the same seeds. 1 means the policy keeps its effectiveness when the adversary adapts.

Before they are shown as business metrics, these indices must be validated (sensitivity across seeds, monotonic response to uncertainty).

## 9. Flagship experiment

**"¿Puede una infraestructura mantener su misión cuando pierde la capacidad de comprender su propio estado?"** (template `flagship_observability`)

- **Initial conditions:** the 13-area reduced SEN at a demanding operating point, generation and demand balanced, digital systems healthy, limited defensive resources.
- **Adversary:** objective "reduce observability / raise uncertainty", adaptive, budgeted.
- **Runs:** policies A, B and C on the same scenario and seeds, with perfect and degraded information, against the static and the adaptive adversary.
- **Results:** supply continuity, detection and understanding time, resources consumed, wrong decisions, response alternatives lost, recovery time, and each policy's sensitivity to uncertainty.

The jury can change a policy, replay the same seed and see the outcome change (`POST /api/v1/sim/runs/{id}/replay`).

## 10. Guardrails and LLM role

The `cyber.md` section 8 guardrails apply in full; item 7 there covers the adversary. In short:

- **Abstract events only.** The adversary acts only through abstract events at area or function level, and its objectives target the defender's decision quality.
- **No ranking.** No output ranks real elements or areas as targets. Campaign results compare defensive policies and capabilities.
- **Notice on every run:** "Escenario hipotético: se modela el efecto, no el ataque."
- **LLM role.** An LLM may interpret evidence and explain decisions (ISR hypothesis text, after-action narrative). It never decides, computes, validates or plays the adversary. It is off by default, and its outputs are recorded in the audit log so replays stay deterministic.
