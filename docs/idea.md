# CascadaSEN: what happens if this power line is cut?

Working name. Platanus Hack 26 Chile (Santiago, 20-22 Nov 2026), track **Simulations**, team-9.
Last updated: 2026-11-21. Written so an agent with no prior context can start working.

Read order for a new session: `idea.md` (this file) -> `stack.md` -> `datasets.md` -> `plan.md`.

## 1. One-paragraph summary

CascadaSEN is an open, interactive blackout simulator for the Chilean national power grid (SEN), running in the browser. The user clicks a transmission line or a power plant on a map of Chile. Within a second the app shows which zones lose power, how many people are affected, and why, as a chain of events in plain language. It also shows what would have prevented the blackout. The model is validated as code against published results of the 25 February 2025 blackout ("25F") and against the grid operator's yearly defence studies.

## 2. Why this problem

- On 25 Feb 2025 at 15:16 the whole country, Arica to Chiloe, lost power. One double-circuit 500 kV line between Atacama and Coquimbo (Nueva Maitencillo - Nueva Pan de Azucar) went out of service. The grid split into two islands and neither survived [3][4].
- Nobody can test "what if another line is cut?" in real life. Today only the grid operator (Coordinador Electrico Nacional, CEN) simulates it, with licensed commercial software (DIgSILENT PowerFactory), and publishes results once a year as PDFs of 100+ pages [5][9].
- People outside the CEN (regulators, academics, consultants, journalists, battery developers) cannot ask "what if" and see the answer.
- Fit with the track: a simplified digital twin of the national grid. It answers "what would happen if X fails?" on something that cannot be tested for real, and the run teaches something not visible at a glance (which failures are harmless, which take down half the country, what prevents it).

Source numbers in brackets refer to `datasets.md` section 7.

## 3. Product

### 3.1 User and decision (hypothesis, no user validated yet)

- Primary user: a technical person outside the CEN who needs to evaluate a grid-security measure without a PowerFactory licence (analyst at the CNE, SEC or Ministry of Energy, academic, consultancy filing comments on CEN reports).
- Decision supported: "Which measure should we ask for or prioritise so a double failure does not end in a total blackout: more automatic load shedding, fast-response batteries in one zone, or finishing a pending defence scheme?"
- Secondary: battery developers (how many MW of fast response an island needs; the model does not say where inside an island), data journalism and education.
- No user has been interviewed. The team must not claim validated demand in the pitch.

### 3.2 Experience (what the user sees)

- Main screen: 2D map of Chile with 3D-style elements on top: generators as columns (height = MW, colour = technology), substations/nodes, transmission lines coloured by voltage, cities as lights. See `stack.md` section 5 for layers and animations.
- Click a line or plant -> "simulate failure". Shift+click adds up to 3 failures.
- Animated cascade (~5 s of story time): flash at the cut, power flow rerouting, overloaded lines turning red and pulsing, the country splitting into two islands, a wave of darkness as cities go out, generator columns dropping.
- Side panels: counter of people without power and MW of load shed; chain of events in plain Spanish from fixed templates (no LLM); frequency curve of each island, synchronised with the animation; validation table (our value / published value / source).
- Selectors: scenario (25F, "midday 2026 with lots of solar", "weekday afternoon", "Sunday"), defence mode ("as on 25F" / "as designed 2026"), behaviour ("everything works to the grid code" / "as it happened on 25F").
- "What would have prevented it?" tab: minimal set of failures that turned a scare into a blackout, MW of fast batteries per island that avoids the collapse, regulatory value of unserved energy.
- Every number shows its source (document and page) or is flagged "assumption" / "approximate". The UI is in Spanish.

### 3.3 Demo script (2 minutes)

1. Hook (15 s): "25 February 2025, 15:16. Chile went dark from Arica to Chiloe. One line was enough."
2. Click (45 s): click that line in the 25F scenario. Country splits, centre-south goes dark, counter rises, narration explains why. Switch to "everything per grid code": the centre-south holds. The difference was generation that disconnected when it should have ridden through (about 1,971 MW disconnected in the centre-south; the CEN model had to add 737.34 MW of unidentified disconnected generation to match measured frequency [4]).
3. Validation (20 s): table "ours / published / source".
4. New question (20 s): "And today? Same cut at midday in 2026 with lots of sun." No PDF answers this.
5. What would have prevented it (20 s).

The 4-minute cut adds a judge clicking anywhere, including a big plant where "nothing serious happens" and the narration explains why. Fallbacks: precomputed JSON cache, recorded video, UI works offline.

## 4. Scope

Priorities are defined in `plan.md`. Short version:

- P0 (no demo without it): public-data network of ~10-14 nodes with sourced parameters, cascade engine plus per-island frequency model with the 25F defences, map with click, islands going dark, people counter, narration, 25F replica in both behaviour modes, first validation cases as tests, validation table in the README.
- P1: 2026 defences, 2026 scenarios, "what would have prevented it", combined failures live, independent validation cases (see `plan.md` section 5).
- P2 / stretch: ambition upgrades (section 6), full official network (Plan A), LLM chat that calls the simulator.

### Out of scope (decided)

Telecommunications, full dynamic simulation like PowerFactory, live monitoring, predicting the human error that started 25F, public ranking of "most dangerous lines" (dual-use risk), full AC voltage model, restoration of service (unless time remains), international interconnections. Voltage is handled by a simplified indicator or flagged "uncertain" (section 5).

## 5. Honest limits (must stay visible in the product)

- It is a reduced network (about 10-14 nodes), not the full SEN, and the screen says so ("red resumida, datos publicos").
- It does not predict 25F. The initiating event was an unauthorised intervention on a protection device [3]. The simulator shows that losing that line left the country dependent on every defence working.
- Frequency is modelled; voltage mostly is not. The CEN's own study says the real limit in the 25F corridor is voltage [6]. The north blacked out about 4 minutes later by voltage collapse [3]. That is shown as a documented event, not a computed one, unless the simplified voltage indicator is built.
- The team decided (2026-11-21) that technical simplifications are acceptable, including a simplified voltage indicator and synthetic parameters, as long as every simplification is labelled on screen ("assumption", "approximate") and kept apart from validated results. Not all data has to be real.
- Parameters that are assumptions: line reactances, load-damping D, reserve time constant, region-to-zone assignment, demand per node in non-25F scenarios.

## 6. Ambition upgrades (proposed, need a team decision)

The independent evaluation scored Ambition 3/5 because plant disconnections are inputs, the north's collapse is documented not computed, and there are no interacting actors. These changes turn inputs into outputs. They are ordered by value per hour; none is in P0.

1. Emergent plant disconnections: each technology (solar, wind, thermal, hydro) has a frequency/voltage ride-through threshold below which it trips. Synthetic thresholds, labelled as assumptions. Then "what would have prevented it" becomes changing a threshold.
2. System inertia as a function of generation mix per island: with lots of solar, frequency falls faster. Makes the "midday 2026" scenario change the physics, not only the data. Adds one term to the existing one-equation-per-island model.
3. Simplified voltage indicator per node (reactive-margin or voltage-drop proxy), labelled "approximate", so the north's collapse can emerge.
4. Automatic N-2 sweep over all pairs of failures with a vulnerability map. Validate by checking that the 500 kV north corridor segments come out as the CEN classifies them (total / partial blackout risk [5]). This is the strongest independent validation and the best answer to "does it teach something new?".
5. Economic and critical-load layer: people, hospitals, Metro, cost via the CNE failure cost (8.79 US$/kWh for the SEN [19]), shown as a regulatory valuation with an editable duration.
6. Defence optimiser: minimum MW of fast batteries or the load-shedding setting that avoids the 25F blackout. A parameter sweep is enough.
7. Restoration phase (how long until power returns): only if the CEN reports contain enough data to fit it.

Do not build an "attacker finds the minimum cut to black out the country" feature. It adds dual-use risk and no judging value.

Exception proposed 2026-11-21 (needs a team decision): a bounded replay of documented cyber incidents, such as the Huatacondo plant in Chile, with a local API for external agents. It stays a catalog of known scenarios, never an optimiser or a ranking. See `attack-sim.md`.

## 7. Hackathon context

- Official rules: https://hack.platan.us/26-cl/bases. Platanus can change rules. Re-read them at the start.
- Judging weights: Technical 25%, Ambition 20%, Execution 20%, Impact 20%, Originality 15%.
- Technical counts the most and the code may be reviewed automatically. Keep the repo clean, with real commits made during the event.
- Rules from the earlier research (verify on the official pages): all team members must be present, remote participation is not allowed, hacking closes Sunday 22 Nov around 08:30-09:00 when repos are locked, only teams with a working demo reach the final, presentations Sunday 09:30-11:30.
- Team (from README): Valentina Honorato, Ricardo Olalquiaga, Alonso Utreras Miranda, Ignacio Montenegro, Felipe Sanhueza Celis. Skills and roles are not recorded. Nobody on the team is known to have power-systems expertise.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Judges see it as a visualiser of PDFs | Open with the click and the validation; show a question no PDF answers (combined failures, "what would have prevented it", N-2 sweep) |
| Validation is partly circular: parameters are fitted on 25F and several tests use the same event | Keep calibration and test sets separate and written down in `plan.md`; add independent cases (CEN classification of north 500 kV segments, loss of 3,000 MW in the 2026 study) to the must-pass set |
| What is genuinely new sits in the "if time" scope | Do not freeze scope until at least one new-question scenario works |
| Line reactances and thermal limits are not public in the sources checked | Use typical values by voltage level and length, calibrated to the 25F flow split, flagged as assumptions |
| A similar project exists: "Andes" (https://github.com/aleetreny/Encode), a 24 h hackathon winner with click-to-fail on the Chilean grid using LP dispatch, without frequency, islands or 25F validation. COSMIC (MATLAB) simulates dynamic cascades | Differentiate on frequency dynamics, islands, 25F validation as visible tests, per-number provenance. Be ready to say so to the jury |
| Dual use (map of "what line blacks out the country") | Zone-level resolution, only failures the CEN already publishes, no public ranking of weak points, language of "failure" not "attack", focus on prevention |
| Live demo failure | Precomputed cache, recorded video, offline mode |
| No power-systems knowledge on the team | Simple documented models, tests against published numbers, ask a mentor early, declare any outside consultation in the README if the organisers allow it |

## 9. Evaluation snapshot

An independent AI evaluation (judge rubric based on the Platanus weights) scored this idea 3.0/5 (each of the five criteria at 3), tied second among six ideas. Its two main criticisms are the circular validation and that the genuinely new content is outside the minimum scope. Both are addressed in sections 6 and 8 and in `plan.md`. The team chose this idea on 2026-11-21.
