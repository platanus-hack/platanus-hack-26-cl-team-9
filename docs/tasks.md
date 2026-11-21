# Tasks

* Infrastructure  - This needs to be a server working (Alonso)
* Agentic setup - (Alonso) - Linter. Always keep memory like mem0 and docs. Update docs. Everything that is backlog, generate an issue

* Check data - (Ricki)
* Define components and actors - Everybody (centrals, cables, cities)
* Map with DeckGL. With a dictionary and we so we can check things (Felipe)


* New features - Vale, Ignacio
* 3D models - Vale, Ignacio
* Animations - Vale, Ignacio
* UI - Vale, Ignacio
* Valores que se mueven en este mercado - Ignacio, vlentina
* Estimar valores y costos del Apagón del 25F en Chile. El hackeo a la central solar de Chile.
* Estudiar Digisilent, se supone que es algo similar
* Count of how many people are affected by blackouts (economical loss, lifes) considering cities - Vale, Ignacio
* Cities, how much population by area. How is a city or population node affected by blackouts

* The system can be handled or managed by an agent somehow. Agents should be able to simulate scenarios
* Animations on attacked infrastructure
  * When infrastructure is cut, attacked or affected (a line, a generator, a substation), the map plays an animation on that object so the viewer sees where the failure starts and what it touches.
  * The animations include audio, so each kind of event has its own sound (for example a cut, an overload, a blackout).
  * Open: which events get which animation and sound, and whether audio is muted by default in the demo.
* Affected people counter
  * Show how many people are affected as a number in the UI. It updates as the simulation plays, so the viewer sees it grow as the failure spreads.
  * The number comes from the population of the cities that lose power. It follows the rule that every number on screen carries a source or `is_assumption: true`.
  * Location in the UI: TBD.
* City lights
  * When a city has issues, the lights in the city turn off on the map.
  * Each city goes dark according to when its island loses power, so the blackout spreads visibly instead of switching off all at once.
* City component (clickable)
  * Cities are components on the map. Clicking one opens its details: its population.
  * The details also show the percentage of that population that depends on electricity. This is a new data point that needs a source or an `is_assumption` flag.
  * If the city has a blackout, its people are affected and the number of deaths rises with time while the blackout lasts.
  * Open: the model for how fast the deaths rise (depends on blackout duration, season and the share of people who depend on electricity), and the source for it. It must be labelled as an assumption until sourced.
* Adversarial agents (backlog, Ricardo)
  * Goal: let agents search for weaknesses and strengths of the grid by attacking it and then analysing the result.
  * Attacker agent: chooses to destroy a generator or a line and runs the simulation to see the consequences.
  * Resilience agent: describes what failed in that scenario and how the system could be strengthened to improve resiliency.
  * We need to enable APIs so the agents can run these simulations and read the results.
  * Deliverables, to be written by Ricardo: a specification of both agents in `docs/`, and a description of how the code should be implemented for this to work.
  * Open questions to settle first: what the attacker maximizes (for example people without power), how many elements it may destroy at once, whether the resilience agent only reports or also proposes changes that are re-simulated, and whether the agents are part of the live demo. Cyber guardrails in `docs/cyber.md` apply: the scenarios model the effect, never the attack technique.

## Future work

* Add APIs so we can collect datasets from other countries and generate the same simulations there.
* 