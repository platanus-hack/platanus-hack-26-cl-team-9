# 0003. DC power flow, with voltage collapse as a rule
Status: Accepted (2026-11-21)

## Context
The model has to answer "what happens if this line goes out" quickly, and the demo has to work without a server (`architecture.md` section 1). The network data is the PyPSA-CL reduced model, which gives reactances and capacities. The real 25F blackout also had a voltage collapse in the north that no DC model reproduces (`stack.md` section 4).

## Decision
- Flow is DC power flow: flow proportional to the angle difference over the reactance, solved per island with numpy (`stack.md` section 4.2). Networks are split into islands with networkx.
- A line opens when its loading is above 120 % of capacity (a parameter), up to 20 stages (`engine.md`).
- Each island has a one-equation frequency model, `df/dt = f0 * dP / (2E)`, with reserve, batteries, load damping and EDAC.
- Voltage is a rule, not a calculation. When the 25F corridor separates with a pre-fault flow above 1,600 MW north to south or 1,000 MW south to north, both islands collapse by voltage (`island_blackout` with `reason: "voltage"`). The health index marks that result uncertain.

## Consequences
- There is no voltage, reactive power or generator ride-through model. The `voltage_limited` result no longer exists in the 188-bus engine.
- The 25F corridor is the only one with published limits, so it is the only one with the voltage rule.
- Results are consequence estimates with listed assumptions, not forecasts (`engine.md`, "Assumptions").
- An AC model (pandapower) is listed as optional, only if the full official network arrives (`stack.md`, simulation engine row of the stack table).

## Sources
`docs/stack.md` sections 4.2 and 4.3, `docs/engine.md` items 4 to 6 and "Assumptions".
