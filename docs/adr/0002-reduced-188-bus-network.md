# 0002. The cascade runs on a 188-bus reduction of PyPSA-CL
Status: Accepted (2026-11-21)

## Context
The plan asked for 10 to 14 nodes (`plan.md` section 9, decision 4). The map needs to show every line a user can cut, and the public PyPSA-CL model has far more elements than that: 1,930 lines and the transformer buses fold into the substations (`mapa3.md` actor A1).

## Decision
Physics runs on a reduction of PyPSA-CL (`domain/cascade/network.py`):
- one bus per substation, transformers folded away, parallel lines merged (capacity added, reactance in parallel);
- 188 buses and 273 lines in 2025 and 2026. Links built after the operating point's year are left out, such as the Kimal-Lo Aguirre HVDC link (2029);
- reactances below 5e-4 pu are raised to that value (an assumption, to keep the solver well conditioned).

The network is pinned to one of four operating points (two hours of Feb 2025 and two of Nov 2026), each with load, generation, inertia and people per bus.

## Consequences
- A click on a map line cuts the whole reduced line. Where circuits run in parallel (the four 500 kV circuits Alto Jahuel to Ancoa) that is the whole corridor, not one circuit.
- Reactances are PyPSA-CL values, not calibrated and not real line data (`engine.md`, 25F check).
- A secure base case (DC-OPF with every line at or below 100 % of capacity and an inertia floor) gives the operating points. N-1 is not imposed, so 10 to 21 lines sit at their limit.
- Other countries' networks use a common schema and are drawn, not simulated (`regional.md`, `network-format.md`).

## Sources
`docs/engine.md` ("What it does" items 1 to 3), `docs/plan.md` section 9 decision 4, `docs/mapa3.md` sections 1.1 and 1.2.
