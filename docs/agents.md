# Agents of the strategic theatre: physical contract

The agents ("bots") of the strategic theatre are described in `strategy.md` section 5: missions, views and permissions. This document covers what they know about the physics and how they act on it. The physics is the 188-bus cascade engine (`engine.md`); parameters for both live in YAML with provenance.

External agents that drive runs over HTTP (not the bots below) use the agent-only OpenAPI spec: `GET /api/v1/agents/openapi.json`, versioned in `docs/openapi/agents.openapi.json`; conventions in `openapi.md`.

Code: `domain/agents/` (agents), `domain/theater/digital.py` (what supervision shows), `domain/theater/grid.py` (per-area physical readings), `domain/theater/params/theater.yaml` → `physics_alarms` (thresholds). Tests: `backend/tests/unit/test_physical_bots.py`.

## 1. Physical contract

### 1.1 What each role sees

The three states of `strategy.md` section 3 still hold:

- **Real state:** the engine, the validator and the evaluator. Never an agent.
- **Observed state:** per area, served MW, the frequency after the last transient (`freq_hz`) and its initial RoCoF (`rocof_hz_s`), all passed through supervision.
  - An area without telemetry or comms shows `None`.
  - Stale data (delay) shows the pre-event steady state, 50 Hz.
  - Unreliable data shows a normal 50 Hz. This is the hardest case, because nothing looks wrong.
  - Fresh data carries noise (`digital.freq_noise_hz`, scaled by uncertainty).
- **Inertia is not observed directly.** Supervision raises a `low_inertia` alarm instead (section 1.4).
- **Voltage is never computed** (section 1.3).

| Role | Physical inputs |
|---|---|
| Stabilisation | Observed `freq_hz` and `rocof_hz_s` per area, plus every physical alarm. Keeps its own estimate (out-of-band areas, voltage-uncertain islands, low-inertia islands) |
| ISR | Physical alarms as evidence with weights (`isr.py` `PHYSICAL`). They count as physical evidence, which points to a failure rather than intent |
| C2 / LLM | Only what reaches C2's view. The LLM context does not carry physical readings yet (open item, section 4) |
| Operations, Logistics | No physical readings; they act on outages, alarms and resources |
| Auditor | The records after each cycle |
| Adversary | Nothing physical. `AdversaryView` has no frequency, RoCoF, inertia or voltage field (`cyber.md` section 8) |

### 1.2 Operating band and thresholds

| Threshold | Value | Provenance |
|---|---|---|
| Operating band | 49.0–51.0 Hz | Assumption. The first EDAC step is 49.0 Hz [4] |
| Steep initial RoCoF | \|df/dt\| ≥ 1.0 Hz/s | Assumption. The 25F reached about 2 Hz/s [4] |
| Low inertia | island E below 31,000 MWs **and** below 90% of the plan for those buses | Floor of the secure base case (`build_baseline_opf.py`). The second condition keeps a midday point (26 GVAs in Nov 2026 13:00) from alarming every cycle when no unit was lost |
| Blackout | 47.5 Hz | NTSyCS art. 3-10 [4] (engine) |

Between operational cycles, secondary control brings energized islands back to 50 Hz (`TheaterGrid.settle_frequency`, assumption). A reading outside the band therefore belongs to the cycle in which a transient happened.

### 1.3 Voltage: documented, not computed

The DC model has no voltage. When a cut opens the 25F boundary and its pre-fault flow was above 1,600 MW N→S or 1,000 MW S→N ([4], `stack.md` 4.6), the 188-bus engine collapses the islands at its ends by a rule: `island_blackout` with `reason: "voltage"` and `result: "blackout"` (`domain/cascade/engine.py` `_settle_island`, `docs/engine.md` item 6). It no longer returns a `voltage_limited` result, so the theatre paths that read one (`domain/theater/execution.py` `_islands`, which maps it to `uncertain`; `domain/theater/digital.py`, which raises the `voltage_limited` alarm for an `uncertain` island; the weight in `domain/agents/isr.py`; the branch in `domain/agents/stabilization.py`) are exercised only by tests that build such a view by hand (`tests/unit/test_physical_bots.py`). Whether to remove them or to map the voltage rule onto them is a pending product decision (`docs/for-reviewers.md`, "Pending product decisions"). No agent claims a voltage value.

### 1.4 Physical alarms

| Alarm | When | Raised by |
|---|---|---|
| `frequency_event` | The island shed load, blacked out or was uncertain in this cycle's transient | `digital.physical_alarms` |
| `frequency_out_of_band` | Observed `freq_hz` outside 49.0–51.0 Hz | `digital.band_alarms` |
| `high_rocof` | Observed \|`rocof_hz_s`\| ≥ 1.0 Hz/s | `digital.band_alarms` |
| `low_inertia` | Island inertia below the floor after losing synchronous units; one alarm per island, only where supervision is visible and reliable | `digital.band_alarms` |
| `voltage_limited` | The island's verdict was `uncertain` (the 188-bus engine does not return it today, section 1.3) | `digital.physical_alarms` |
| `load_loss`, `blackout`, `breaker_open` | Unchanged | `digital.physical_alarms` |

Physical alarms are never drawn as false alarms. Their thresholds live in `theater.yaml` → `physics_alarms` and are merged into `TheaterConfig.digital`.

## 2. Rules per role

### 2.1 Stabilisation (`agents/stabilization.py`)

All checks run on its own estimate, never on the real grid.

| Situation (estimate) | Proposal | Rationale key |
|---|---|---|
| `high_rocof` or `low_inertia` | `battery_support` (acts in 0.5 s), priority areas first | `stab_fast_support_low_inertia` |
| Area observed below 49.0 Hz | `fast_reserve` there | `stab_reserve_under_frequency` |
| Load shed or collapse seen, or a preemptive posture | `battery_support` / `fast_reserve` for the first priority area | `stab_fast_support_priority_area`, `stab_reserve_priority_area` |
| Under-frequency and no battery or reserve left | `preventive_load_reduction` in a non-priority area of the low island | `stab_preventive_margin` |
| `defense_fault` | `rearm_defense` | `stab_rearm_defense` |

| Veto | When | Reason |
|---|---|---|
| `restore_element` (area or corridor) | Its island is voltage-uncertain (this cycle and the next) | `stab_voltage_uncertain` |
| `restore_element` (area) | The island is still swinging (cycle of a shed or collapse and the next), or the area is out of band | `stab_wait_for_stability` |
| `islanding_prep` | Either side of the corridor raised `low_inertia` | `stab_low_inertia` |

### 2.2 ISR

The new alarms add evidence per area. Weights: `frequency_out_of_band` 0.4, `high_rocof` 0.3, `low_inertia` 0.2, `voltage_limited` 0.3. They are physical evidence and never raise the suspicion of an intentional cause.

### 2.3 C2 and the LLM

C2 still decides on the rules plus the optional LLM pick (`strategy.md` section 10). The LLM sees only C2's view.

### 2.4 External agents

An agent running on another machine works through a shared session (`docs/sessions-api.md`): it creates or joins a session, then passes the session id in the path of every call (`/api/v1/sessions/{sid}/...`). It can edit the session network, open and repair lines in the sandbox, and drive runs nested in the session, including `POST /sessions/{sid}/runs/{rid}/actions`, which queues its own course of action for the next cycle. That action skips C2's choice, its operator attention cap and the conflict rules, but goes through the same validator, resources and crews as the commander's approved actions when it executes (it still spends one unit of operator attention), and is logged with the agent's name. The guardrails of section 3 apply to it. A client with an LLM can drive the same API in natural language through the MCP server (`docs/mcp.md`).

## 3. Guardrails

- The adversary is blind to physics. Its view never gets a physical quantity, and its arms stay areas, zones and defence functions (`strategy.md` 5.1).
- No ranking. Physical readings describe consequences and never rank elements as targets (`cyber.md` section 8).
- Every threshold carries a source or `is_assumption`.

## 4. Pending work (not done yet, 2026-11-21)

| # | Pending | Where | Note |
|---|---|---|---|
| 1 | Physical summary in the LLM commander's context: islands, observed f, out-of-band areas, uncertain flags; the prompt explains the 49–51 Hz band and that "incierto" means voltage is not computed | `theater/cycle.py` (`_llm_pick` context), `infrastructure/llm.py` (prompt) | Only from C2's view. Left out because both files were being edited in parallel on `feat/strategic-sim-api` |
| 2 | Draw the physical readings in the operation view (frequency per area, RoCoF, physical alarms, "limitado por tensión (incierto)") | Frontend operation view (removed from `feat/strategic-sim-api`, which is backend only; it returns in a frontend PR) | The snapshot's `observed.areas` already holds `freq_hz` and `rocof_hz_s`; `transient.islands` holds `min_hz`, `final_hz`, `rocof_hz_s`, `inertia_mws`. Update `mapa3.md` section 10 with it |
| 3 | Release fast reserve and battery blocks (duration or energy limit) | `theater/execution.py` (`apply_action`, `tick`), `theater/resources.py` | Today they stay held until the area blacks out. `restoration.reserve_recovery` in `theater.yaml` is unused: wire it up or remove it |
| 4 | Regenerate the map's cached cuts | `uv run cascadasen-cache` → `web/public/cache/` | The engine changed (extreme EDAC, droop, new summary fields); the cache is stale until then |
| 5 | `low_inertia` repeats every cycle while an island stays below the floor (12–13 times in the flagship run after the 900 MW loss) | `theater/digital.py` (`band_alarms`) | True condition but noisy for ISR. Option: raise it only when inertia drops further or on the first cycle below the floor |
| 6 | The low-inertia floor (31,000 MWs) is a system-level figure applied per island | `theater.yaml` → `physics_alarms` | Needs a per-island criterion if a source exists |
| 7 | Calibrate the island frequency on this network against the CEN 25F numbers (V2–V9); only the V1 flow split is checked | `domain/cascade/`, `tests/unit/test_cascade.py` | The 13-area engine keeps those cases (`engine.md`) |
