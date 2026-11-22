# 0001. Two simulation engines: 13 areas and 188 buses
Status: Accepted (2026-11-21)

## Context
The first plan modelled Chile as 10 to 14 aggregated nodes along the north-south trunk (`stack.md` section 4.1). The validation cases V1 to V10 (`plan.md` section 5) were written for that model, and the 25F replica is checked against published CEN numbers. Later the team built a 188-bus reduction of PyPSA-CL to draw cuts on the real map (`engine.md`).

## Decision
Keep both engines.
- `domain/simulation/` is the 13-area engine. It serves only `POST /api/v1/simulate` and the validation cases V1 to V10.
- `domain/cascade/` is the 188-bus engine. It serves the map's cached cuts, shared sessions and the strategic theatre, which groups the buses into 13 operating areas by latitude band (`strategy.md` section 2.1).

## Consequences
- Some concepts exist twice (island frequency in `simulation/frequency.py` and `cascade/frequency.py`, parameters, events). A fix to one engine does not reach the other.
- Only the V1 flow split is checked on the 188-bus network. Calibrating its island frequency against the CEN 25F numbers (V2 to V9) is not done (`engine.md`, "Not done").
- Both engines load parameters with the loader in `domain/simulation/params.py`, which rejects numbers without `source` or `is_assumption`.
- Merging the engines would mean re-running V1 to V10 on the 188-bus network. It is a separate piece of work.

## Sources
`docs/engine.md` (intro, "Not done"), `docs/architecture.md` section 2.2, `docs/plan.md` section 9 decision 4, `docs/stack.md` section 4.
