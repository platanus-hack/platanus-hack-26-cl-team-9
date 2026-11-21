# Scenarios of mapa 3

The selector at the top of mapa 3 ("pill") lists ready-made cases. Each one is an operating point (a base hour) with or without a cut. This file explains every scenario, in detail for the two that are not obvious: the Alto Jahuel–Ancoa cut and the S/E Charrúa fault.

Tags: EVIDENCE = read from the cache, the code or a cited source. ASSUMPTION = a modelling choice, not verified.

UI strings are Spanish. This document is English.

## 1. How scenarios work

- A scenario is `point` + `cut`, defined in `web/src/cascade/scenarios.ts`.
- `point` is a folder in `web/public/cache/` (`feb2025-1500`, `feb2025-0300`, `nov2026-1300`, `nov2026-2000`).
- `cut` is a file in that folder: a line id (`R239.json`), a named cut (`falla-charrua-2010.json`) or `null` for the base case (`baseline.json`).
- Picking a scenario loads that file and plays the cascade. A line you cut by clicking the map shows as "Corte manual".
- Named cuts are built by the cache builder (`NAMED_CUTS` in `backend/src/cascadasen/application/cache_builder.py`): every line of one substation opens at t = 0.

To add a scenario: add the cut to `NAMED_CUTS` (or use a line id), run `cascadasen-cache`, and add one entry to `SCENARIOS`. The test `scenarios.test.ts` checks that ids are unique.

## 2. List

Numbers are what the committed cache shows today (see section 6 about the engine version).

| Id | Name in the selector | Point | Cut | People without power | MW lost | Stages |
|---|---|---|---|---|---|---|
| `dia-normal` | Día normal · febrero 2025, 15:00 | `feb2025-1500` | none | 0 | 0 | 0 |
| `noche-normal` | Noche normal · febrero 2025, 03:00 | `feb2025-0300` | none | 0 | 0 | 0 |
| `mediodia-solar-2026` | Mediodía solar · noviembre 2026, 13:00 | `nov2026-1300` | none | 0 | 0 | 0 |
| `punta-2026` | Punta nocturna · noviembre 2026, 20:00 | `nov2026-2000` | none | 0 | 0 | 0 |
| `25f` | Corte del 25F · febrero 2025, 15:00 | `feb2025-1500` | `R239` | 15.2 M | 7,872 | 2 |
| `25f-noche` | Mismo corte de noche · febrero 2025, 03:00 | `feb2025-0300` | `R239` | 307,408 | 631 | 2 |
| `25f-2026` | Mismo corte con la red de 2026 · mediodía solar | `nov2026-1300` | `R239` | 15.4 M | 7,347 | 2 |
| `alto-jahuel-ancoa` | Corte Alto Jahuel – Ancoa 500 kV · punta nocturna 2026 | `nov2026-2000` | `R006` | 3.2 M | 2,118 | 5 |
| `charrua-2010` | Falla en S/E Charrúa · análogo del 14 mar 2010 · punta nocturna 2026 | `nov2026-2000` | `falla-charrua-2010` | 4.5 M | 2,612 | 2 |

The four base hours come from PyPSA-CL demand and the secure DC-OPF base case (`docs/engine.md`). They have no cut, so nothing fails.

## 3. Corte Alto Jahuel – Ancoa 500 kV (`R006`)

### What it is

`R006` is the 500 kV line between the substations Alto Jahuel (south of Santiago) and Ancoa (Maule region). It is the main link that moves power from the south and the center of the country to the Santiago area. In the reduced model it is one line of 2,800 MW capacity (EVIDENCE: `network-2026.json`).

### Why this case

At night the south exports power north through this corridor. With the 2026 network at the evening peak (20:00) it carries 1,172 MW from Ancoa toward Alto Jahuel, 42% of its capacity (EVIDENCE: `nov2026-2000/baseline.json`). Cutting it forces that power onto the 220 and 154 kV network of the Maule region, which cannot carry it, so lines trip one after another. It is a case where an N-1 cut does not stay N-1.

The same cut does nothing at 15:00 (no stage) because at midday the corridor carries little. At 03:00 on the 2025 network it blacks out the whole system (16.97 M people, 8,719 of 8,719 MW). That result depends on uncalibrated assumptions, so it is not offered as a scenario.

### Relation to the 24 September 2011 blackout

On 24 September 2011 a fault at the Ancoa substation left 9 to 10 million people without power between La Serena and Talca, from about 20:30 ([BioBioChile](https://www.biobiochile.cl/noticias/2011/09/24/apagon-afecta-a-gran-parte-de-la-zona-centro-norte-del-pais.shtml); the SEC charged Transelec, Endesa, Colbún and Chilectra, per [DF](https://www.df.cl/empresas/energia/sec-formula-cargos-contra-transelec-endesa-colbun-y-chilectra-por-el)). This scenario is an ASSUMPTION-level analogue: same area, same time of day, but on today's network. It is not a reproduction, and the selector name does not claim it.

### What happens, step by step

EVIDENCE: `nov2026-2000/R006.json` in the committed cache.

| Time | Event |
|---|---|
| 0.0 s | The line opens. One island of 188 buses (10,934 MW generation and demand). |
| 1.0 s | Colbún – Puente Negro (220 kV, 680 MW) exceeds 120% and opens. |
| 2.0 s | Itahue – Tinguiririca (154 kV, 198 MW) opens. |
| 3.0 s | Itahue – Teno (154 kV, 198 MW) opens. The grid splits: 129 buses (7,088 MW generation, 8,535 MW demand) and 59 buses (3,846 MW generation, 2,399 MW demand). The first island has a deficit, so EDAC sheds about 850 MW in steps between 3.26 and 3.92 s. |
| 4.0 s | Cautín – Río Toltén (220 kV, 183 MW) opens. New islands of 42 and 17 buses. |
| 4.77 s | The 17-bus island (756 MW of demand) falls under 47.5 Hz (47.498 Hz) and blacks out. |
| 5.0 s | Lautaro – Temuco (66 kV, 50 MW) opens. A 1-bus island of 88 MW of demand blacks out at 5.37 s. |
| 23 to 25 s | The remaining islands settle between 48.7 and 51.1 Hz. |

Result: 3.18 million people, 2,118 of 10,934 MW (19%), 5 stages, two islands in blackout.

### How to read it

- The first trips are small 220 and 154 kV lines in the Maule region, far from the cut. That is the cascade: the cut moves flow onto weaker lines.
- The damage is in the south-center: the dark substations are the ones in the islands that lose frequency control.
- Santiago and the north stay lit. They lose 1,172 MW of imports, which EDAC and the local generation cover.

### Limits

- DC flow without voltage: voltage collapse is not computed.
- The 120% opening threshold and 1 s between stages are assumptions (`docs/engine.md`).
- The cut is the whole merged line, which may be more than one real circuit.
- People without power uses the known `people` defect (some substations have load and 0 people), so read it as a lower bound.

## 4. Falla en S/E Charrúa (análogo del 14 de marzo de 2010)

### What happened on 14 March 2010

- On 27 February 2010 a magnitude 8.8 earthquake hit central Chile. Two weeks later, on Sunday 14 March at 20:43, a 500/220 kV transformer of 750 MVA at the Charrúa substation (Biobío) failed. The transformer had been damaged by the earthquake and its aftershocks ([BioBioChile](https://www.biobiochile.cl/noticias/2010/03/17/transelec-repara-transformador-de-subestacion-charrua-que-provoco-apagon-del-domingo.shtml)).
- Charrúa gathers the energy of several large power plants and is where the 500 kV system toward the Santiago region starts ([Cooperativa](https://www.cooperativa.cl/noticias/pais/energia/generacion-electrica/centro-de-despacho-de-energia-confirmo-falla-en-transformador-en-charrua/2010-03-14/224613.html)).
- The result was a blackout of the whole SIC, from Taltal to Chiloé, affecting more than 13 million people ([La Tercera](https://www.latercera.com/noticia/corte-suprema-ratifica-sanciones-a-electricas-por-corte-de-2010-y-aplica-multas-de-3-000-millones/)). About 90% of the service was back after three hours, but the Biobío region stayed dark longer ([BBC](https://www.bbc.com/mundo/america_latina/2010/03/100314_0135_chile_apagon_jrg)). The SEC charged 115 companies of the CDEC-SIC ([La Tercera](https://www.latercera.com/noticia/sec-formulo-cargos-a-115-empresas-electricas-por-apagon-del-14-de-marzo/)).

Content was rephrased for compliance with licensing restrictions.

### How we represent it

The reduced model folds transformers into the lines, so the transformer of Charrúa does not exist as an element. These assumptions fill the gap:

1. **ASSUMPTION:** a fault at the substation is represented as the substation out of service: all 16 lines that end at S/E Charrúa open at t = 0 (`NAMED_CUTS["falla-charrua-2010"]` = `"S/E CHARRUA"`).
2. **ASSUMPTION:** the base is the 2026 evening peak (`nov2026-2000`), because it is the closest hour we have to a Sunday at 20:43. The real event was in March (autumn), the case is November 2026.
3. **ASSUMPTION:** no pre-existing damage. The post-earthquake state of the network (other lines or substations already out of service or limited) is not in the repo and we did not invent it.

The 16 lines (EVIDENCE: `network-2026.json`):

| To | Voltage | Capacity | Id |
|---|---|---|---|
| Entre Ríos | 500 kV | 2,570 MW | `R104` |
| Ancoa (aux) | 500 kV | 2,078 MW | `R030` |
| Los Notros | 220 kV | 1,097 MW | `R107` |
| Antuco | 220 kV | 1,023 MW | `R040` |
| Mulchén | 220 kV | 549 MW | `R108` |
| Central Santa María | 220 kV | 517 MW | `R083` |
| Concepción | 220 kV | 428 MW | `R102` |
| Lagunillas | 220 kV | 367 MW | `R106` |
| Cholguán (STS) | 220 kV | 343 MW | `R100` |
| Trupán | 220 kV | 274 MW | `R111` |
| Duqueco | 220 kV | 264 MW | `R103` |
| Hualpén | 220 kV | 227 MW | `R105` |
| Chillán | 154 kV | 188 MW | `R099` |
| Parral | 154 kV | 107 MW | `R109` |
| Santa Elvira | 154 kV | 75 MW | `R110` |
| Cholguán (Transelec) | 66 kV | 53 MW | `R101` |

Before the cut these lines carry 2,682 MW in total (sum of absolute flows, EVIDENCE: `nov2026-2000/baseline.json`; three lines had no flow recorded).

### What the engine gives

EVIDENCE: `nov2026-2000/falla-charrua-2010.json`, built with the current engine.

| Time | Event |
|---|---|
| 0.0 s | 16 lines open. Four islands: 155 buses (8,158 MW generation, 9,345 MW demand, a deficit), 28 buses (2,571 MW generation, 1,117 MW demand, a surplus), and two 1-bus islands. The substation itself (36 MW generation, 264 MW demand) is one of them. |
| 0.03 to 0.45 s | EDAC sheds load in the deficit island. |
| 0.26 s | The Charrúa 1-bus island (264 MW) falls under 47.5 Hz and blacks out. |
| 1.0 s | One line opens by overload. Islands of 17 and 11 buses. |
| 1.4 s | The 17-bus island (756 MW) blacks out. |
| 2.0 s | One more line opens. A 1-bus island of 88 MW blacks out at 2.34 s. |
| 11.8 s | A 10-bus island (273 MW) blacks out. |
| 20 s | The remaining islands settle. |

Result: 4.54 million people, 2,612 of 10,934 MW (24%), 2 stages. The map shows the south (Biobío to Araucanía) dark.

### What differs from the real event

- **Scale.** The real blackout covered the whole SIC (more than 13 M people). The model gives 4.5 M. The model does not reproduce a total blackout.
- **ASSUMPTION on the cause of the gap:** in 2010 the SIC had weak protection and defence schemes. The SEC charged the companies for it. The engine assumes EDAC works as designed and does not model failures of the schemes, so it underestimates the spread.
- The 2010 SIC was not connected to the north (the SING) and had no Cardones – Polpaico 500 kV line. The model uses the 2026 national network.
- The transformer (750 MVA, one of several) is not a separate element. Taking out the whole substation removes more than the real fault did.
- The real event restarted in about three hours. The model has no restoration.

Use the case as: "what would the loss of the Charrúa substation do to today's network at the evening peak". Do not present it as a reproduction of 2010.

### How to make it closer

1. Get the post-earthquake state: the CDEC-SIC report of the event lists the elements out of service on 14 March 2010. They can be set as already open lines (the engine can start from a running state, commit `c8b0aef`).
2. Replace "all lines out" by the loss of the Charrúa 500/220 kV transformation only: needs transformers as elements in the reduced network.
3. Add the failure of the defence schemes as a parameter.

## 5. The 25F cut (`25f`, `25f-noche`, `25f-2026`)

`R239` is Nueva Maitencillo – Nueva Pan de Azúcar 500 kV (2,210 MW), the corridor that failed on 25 February 2025. See `docs/mapa3.md` section 6 and `docs/engine.md`.

## 6. Engine version and the cache (read before trusting the numbers)

EVIDENCE: the cache committed in `main` (commit `420ba53`) was built before the engine change `58f8b74` ("provenance params, droop, batteries, extreme EDAC and voltage verdict"). Running the current engine gives different numbers for some scenarios:

| Scenario | Committed cache (the site today) | Current engine |
|---|---|---|
| `25f` | 15.2 M people, 7,872 MW, 2 stages | 3.8 M people, 1,972 MW, 2 stages, `uncertain = true` |
| `25f-noche` | 307,408 people, 631 MW | the same |
| `25f-2026` | 15.4 M people, 7,347 MW, 2 stages | 5.6 M people, 2,649 MW, 3 stages, `uncertain = true` |
| `alto-jahuel-ancoa` | 3.2 M people, 2,118 MW, 5 stages | 3.4 M people, 2,160 MW, 5 stages |

The new engine marks a result as `uncertain` when the 25F boundary opens with a pre-fault flow outside the validity range of the defence scheme: it documents a voltage limit instead of computing it (`_voltage_verdict` in `engine.py`). The web app does not show that flag yet.

Only the new named-cut files (`falla-charrua-2010.json`, 4 files) were built with the current engine. Decision pending for whoever owns the engine: regenerate the whole cache (`cascadasen-cache`) and show the `uncertain` flag, or keep the old cache. Until then the site mixes both versions.
