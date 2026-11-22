# Revisión técnica del repositorio Sub50 / CascadaSEN

Equipo 9, Platanus Hack 26. Criterio evaluado: "Aspecto técnico" (25 %), issue #79 "Evaluación técnica de todo el repositorio según los criterios de Platanus Hack 26".
Commit auditado: `8664add` (rama local `main`, merge del PR #78 "regenerar-cache"). Fecha de la auditoría: 2026-11-21.
Auditoría de solo lectura: no se editó código, no hubo commits, push, issues ni acceso a AWS o Terraform. Este archivo es el único artefacto creado y queda sin commitear.

> **Advertencia de alcance (leer primero).** `8664add` no es la punta de `upstream/main`. Con las referencias locales de este clon, `git rev-list --count HEAD..upstream/main` da **32** commits de diferencia (`upstream/main` = `03d2d5b`, 2026-11-21 23:37; `origin/main`, el fork, está en `0158bd5`). Esos commits agregan el chat del asistente en la web (`web/src/assistant/*`), costo e índice de salud, mapas de calor de dependencia y criticidad, regeneran los 1.852 JSON de `web/public/cache` y **eliminan el symlink `web/node_modules`** (`965c0a3`). Tocan además `engine.py`, `test_grid_simulation.py`, `docs/stack.md`, `docs/plan.md` y `web/package.json`. No cambian `.github/`, `scripts/` ni `limits.py`. Los hallazgos marcados "posible corrección upstream" pueden estar resueltos allá. No ejecuté ninguna herramienta sobre `upstream/main`.

---

## 1. Resumen ejecutivo

**Puntaje global estimado para "Aspecto técnico": 3,5 / 5** (rango razonable 3,0 a 4,0 según cuánto pese una revisión automática).

Razonamiento:

- El núcleo de ingeniería es sólido y verificable. El dominio no importa nada de las capas externas (0 violaciones en la matriz de imports), el motor sigue `docs/engine.md` paso a paso, los parámetros no cargan sin `source` o `is_assumption`, el teatro de simulación es determinista y las validaciones V1 a V10 son tests reales con tolerancias. `ruff` está limpio, `tsc` da 0 errores y la cobertura backend es 89 %.
- La nota baja por la capa de proceso y por la forma del código. Ningún workflow ejecuta pytest, vitest, mypy ni `tsc`, y `deploy.yml` publica cada push a `main` sin compuerta de pruebas. Con ese hueco, la rama principal tiene hoy 3 tests en rojo. El README raíz sigue siendo la plantilla del hackathon. `mypy` da 179 errores. Hay funciones de 150 a 325 líneas y un componente React de 530 líneas.
- El costo de subir la nota es bajo. Los cuatro arreglos de mayor efecto (CI con pruebas, suite en verde, README raíz, cabeceras de docs obsoletas) suman unas 16 horas y llevarían la estimación a cerca de 4,0.

**Fortalezas principales**

1. Regla hexagonal respetada en el dominio, sin ciclos de import a nivel de módulo (sección 4.8).
2. Supuestos con proveniencia obligatoria en código y probada en test (`domain/simulation/params.py:47-48`, `test_cascade.py:311-316`).
3. Determinismo del teatro: flujos de azar derivados con SHA-256, independientes de `PYTHONHASHSEED` (`domain/theater/rng.py:14-17`).
4. Concurrencia de sesiones diseñada con cuidado: `If-Match`, lock por sesión con tope de espera, límites de tasa y de tamaño (`api/limits.py`, `application/sessions.py:174-211`).
5. Contratos que se prueban solos: el OpenAPI de agentes tiene un test de deriva, y las 31 rutas de sesión coinciden con `docs/sessions-api.md`.

**Riesgos principales**

1. Sin pruebas en CI y despliegue sin compuerta (`.github/workflows/lint.yml`, `deploy.yml:6-9`). Alta.
2. README raíz es la plantilla (`README.md`, 0 menciones de Sub50). Alta.
3. 3 tests en rojo en `main`, entre ellos la deriva de la caché versionada respecto del motor (`engine.py:417`). Media.
4. `mypy`: 179 errores sin configuración ni CI. Media.
5. Funciones gigantes (`validate_snapshot` 325 líneas, cc 137) y `CascadeApp` de 530 líneas. Media.

---

## 2. Alcance y método

**Qué se auditó:** `backend/` (118 `.py` en `src`, 43 en `tests`), `web/src` (72 archivos), `data/scripts` (5 archivos), `.github/workflows`, `scripts/`, `docs/`, `README.md`, `AGENTS.md`, `CHANGELOG.md`, y el historial git (secretos, higiene de commits).

**Qué se ejecutó** (todo en el worktree `.worktrees/code-audit`, sin modificar fuentes):

| Herramienta | Comando |
|---|---|
| ruff | `uv run ruff check .` y `uv run ruff format --check .` (en `backend/`) |
| mypy | `uv run mypy src` (sin `[tool.mypy]`, configuración por defecto) |
| pytest + cobertura | `uv run --with pytest-cov pytest --cov=cascadasen --cov-report=term-missing -q` |
| tsc / vitest / build | `npm ci`, `npx tsc --noEmit`, `npx vitest run`, `npm run build` (en `web/`) |
| Métricas propias | AST (`scripts/metrics.py`: grafo de imports, longitud y complejidad de funciones, excepciones), `radon cc/mi/raw`, `vulture`, `pylint --enable=duplicate-code`, `gitleaks` 8.30.1, barrido de patrones sobre árbol e historial, comparación de rutas reales contra docs, 3 corridas con `PYTHONHASHSEED` distinto |
| Verificación final de este informe | 36 referencias `archivo:línea` abiertas en el worktree (sección 9.2) |

**Fuera de alcance:** infraestructura (`*.tf`, `deploy.sh`, Dockerfiles más allá de los comandos que ejecutan), AWS, Terraform, cualquier cambio de código, apertura de issues. No se corrió ninguna herramienta sobre `upstream/main` (ver advertencia de alcance).

**Convención de ids:** `B-xx` backend, `W-xx` web, `D-xx` scripts de datos, `R-xx` repositorio transversal. Cuando dos hallazgos eran el mismo, se fusionaron y el id secundario aparece en "también". Severidad: alta, media, baja. Las horas son estimaciones gruesas.

---

## 3. Tabla de puntajes

| Área | Puntaje | Justificación |
|---|---|---|
| Backend dominio | **4 / 5** | Motor de 188 barras fiel a `docs/engine.md`, supuestos obligatorios, azar con semilla, V1-V10 como tests. Resta: dos motores de frecuencia separados con solo uno validado (B-03), camino de voltaje obsoleto tras el PR #76 (B-06), funciones de 150 a 325 líneas (B-09). |
| Backend application / api / infrastructure | **3,5 / 5** | Validación de entrada, concurrencia optimista, límites y test de deriva del OpenAPI; 89 % de cobertura. Resta: tope de cuerpo que omite peticiones chunked (B-04), endpoint de campañas sin límite (B-05), fugas de capas con 2 ciclos (B-08), 179 errores de mypy (R-03), adaptadores de fuentes reales al 28-30 % de cobertura (R-05). |
| MCP / asistente | **4 / 5** | Una sola capa de herramientas alimenta el servidor MCP y el asistente; las barreras (sin ranking, cortes de 1 a 3 líneas, MW solo si el usuario lo dice, `end_session` retenido) están en código. Resta: sin autenticación ni tope diario de costo en un endpoint LLM de pago (B-17), test de barrera por nombre (B-07), servidor MCP no cubierto por la suite por defecto (B-12). |
| Frontend | **3,5 / 5** | `tsc` 0 errores, un solo `any`, sin `innerHTML`, cliente de sesión con reintentos 409/412 y 74 tests. Resta: `CascadeApp` de 530 líneas y 61 hooks sin test (W-01), sin lint ni CI para `web/` (R-04), constantes copiadas a mano del backend (W-05), sin tests de componentes (W-04). |
| Scripts de datos | **3 / 5** | Reconstrucción determinista (`node_index.json` idéntico byte a byte), docstrings con el porqué y autochequeos. Resta: descarga con `curl` sin `-f` que puede guardar HTML como `.xlsx` (D-01), `scipy` no declarado (R-23), fuera de lint, tests y CI (D-02), salidas sin cabecera de proveniencia (D-03). |
| Tests y CI | **3 / 5** | Suite amplia con aserciones de resultado (357 tests, 994 `assert`, 380 pasan, 89 %). Resta: ningún workflow corre pytest, vitest, mypy ni `tsc`; 3 tests en rojo en `main`; sin cobertura configurada ni medida en web. |
| Documentación del código | **3,5 / 5** | 106 de 106 módulos con docstring que cita la sección de doc y el porqué; rutas y OpenAPI coinciden con los docs. Resta: README raíz de plantilla (R-14), cabeceras obsoletas en `stack.md` y `plan.md` (R-15), 25 % de funciones con docstring y 55 funciones de 40 o más líneas sin ninguna (R-16). |
| Modularidad | **3,5 / 5** | Dominio sin imports externos, sin ciclos a nivel de módulo, duplicación textual baja (0 bloques de 10 líneas). Resta: 51 funciones sobre 50 líneas, capa de herramientas MCP alojada en el paquete de un cliente, 2 ciclos con imports locales, 15 o más constantes duplicadas entre `web/` y `backend/`. |

Promedio simple de las ocho áreas: 3,5. Peso mayor a la calidad del diseño del dominio y a las decisiones documentadas que a la capa de proceso, porque el criterio dice "calidad de ingeniería y decisiones de diseño". Si el revisor automático pondera sobre todo CI, tipos y README, el resultado se acerca a 3,0.

---

## 4. Resultados de herramientas

Salidas completas en `/tmp/code-audit/raw/`. Apéndice (sección 10) con los extractos.

### 4.1 ruff check

`uv run ruff check .` en `backend/`: **PASA**, "All checks passed!", exit 0. Supresiones en `src`: 2 `# noqa: E731` (`domain/regional_reduction.py:444`, `domain/regional_network.py:220`), 0 `TODO/FIXME`.

### 4.2 ruff format

`uv run ruff format --check .`: **PASA**, "162 files already formatted", exit 0, 0 diferencias. CI fija `ruff==0.17.6` (`lint.yml:17`), igual que `backend/uv.lock`.

### 4.3 mypy

`uv run mypy src`: **FALLA**, exit 1. **179 errores en 33 de 118 archivos.** No existe `[tool.mypy]` en `backend/pyproject.toml`, así que corre con valores por defecto.

| Código | N | Código | N |
|---|---|---|---|
| arg-type | 52 | var-annotated | 7 |
| attr-defined | 24 | index | 7 |
| union-attr | 16 | operator | 6 |
| misc | 16 | type-var / return-value / list-item | 4 cada uno |
| import-untyped | 14 | import-not-found / dict-item / call-arg | 2 cada uno |
| assignment | 10 | call-overload | 9 |

16 de los 179 vienen del entorno (14 `import-untyped` por falta de stubs de networkx, yaml, openpyxl, boto3, botocore; 2 `import-not-found` por `anthropic` y `mcp.server.mcpserver`). Los 163 restantes están en el código, concentrados en `domain/unify.py` (22), `domain/validation.py` (18), `domain/theater/execution.py` (18), `api/session_schemas.py` (16), `domain/simulation/engine.py` (15). La mayoría son `float | None` pasado donde se espera `float`. Ejemplo con consecuencia de diseño: `api/session_routes.py:222` ("Missing named argument label for SessionCreate") y `:371`, `:397` (el modelo dinámico de `create_model` no expone `model_dump`; ya hay `# type: ignore[valid-type]` en `:366` y `:392`).

### 4.4 pytest con cobertura

`uv run --with pytest-cov pytest --cov=cascadasen --cov-report=term-missing -q`: **380 pasan, 3 fallan, 4 omitidos**, 1 advertencia, 27,4 s. **Cobertura total 89 %** (11.915 sentencias, 1.329 sin cubrir). Tabla completa en el apéndice.

Fallos:

1. `tests/unit/test_llm_commander.py::test_bedrock_adapters_use_the_aws_profile`: `ModuleNotFoundError: No module named 'anthropic'` (`:130`, `import anthropic` sin `importorskip`; `anthropic` está en el extra opcional `llm`).
2. `tests/unit/test_grid_simulation.py::test_the_committed_cache_matches_the_engine_for_a_single_cut[feb2025-1500-R239]`.
3. Mismo test con `[nov2026-2000-R001]`. Compara `web/public/cache/<punto>/<línea>.json` con la salida actual del motor por igualdad exacta (`:80-84`). La comparación celda por celda (`raw/cachediff.txt`) muestra 7 diferencias en total, todas con `loading` = 1,0 en ambos lados: `R183.status` (motor `ok`, caché `overload`); `R113.flow_mw` -40 contra -39; `R113` y `R206` `overload` contra `ok`; `R122` y `R065` al revés. Son vuelcos de umbral en el límite exacto de 100 %. Causa probable: el estado se decide con `ratio > 1.0` sobre ruido de coma flotante (`domain/cascade/engine.py:417`) y el caso base fija hasta 21 líneas justo en 100 % (`docs/engine.md`, paso 3). No investigué más allá del diff.

Omitidos: `tests/integration/test_mcp_server.py:9` y `tests/unit/test_mcp_tools.py:6` (paquete `mcp` no instalado, por eso `mcp/server.py` queda en 0 %); `tests/validation/test_engine_cases.py:96` (V6, falta la clasificación del CEN) y `:123` (V9, falta la curva digitalizada de Polpaico).

Cobertura por paquete:

| Paquete | Sentencias | Sin cubrir | Cobertura |
|---|---|---|---|
| domain | 7.169 | 439 | 93,9 % |
| api | 1.249 | 64 | 94,9 % |
| application | 1.798 | 296 | 83,5 % |
| infrastructure | 1.212 | 347 | 71,4 % |
| mcp | 407 | 141 | 65,4 % |
| raíz (`cli.py`, `sim_fixtures.py`) | 80 | 42 | 47,5 % |
| **Total** | 11.915 | 1.329 | **89 %** |

29 módulos al 100 %, 12 bajo 50 %, 23 bajo 80 %. Más bajos: `mcp/server.py` 0 %, `cli.py` 0 %, `infrastructure/arcgis.py` 16 %, `ide_energia.py` 28 %, `pypsa_cl.py` 29 %, `infotecnica.py` 30 %, `ine_censo.py` 30 %, `application/cache_builder.py` 33 %, `infrastructure/http.py` 36 %, `build_regional.py` 42 %, `domain/topology_inference.py` 56 %. Los cuatro adaptadores de fuentes reales alimentan el unificador de toda la red; `test_unify.py` usa un `SourceBundle` sintético.

### 4.5 tsc

`npx tsc --noEmit` en `web/` (TypeScript 7): **PASA**, exit 0, **0 errores**. `npm run build` ejecuta `tsc --noEmit && vite build` (`web/package.json`, script `build`), y la imagen web de producción corre ese build (`infrastructure/docker/web.Dockerfile:12`), de modo que un error de tipos ya detiene el despliegue de la imagen web.

### 4.6 vitest

`npx vitest run` (v5.1.1): **PASA**, exit 0. **13 archivos, 74 tests pasan, 0 fallan**, 0,66 s. Cobertura web **no medida**: `@vitest/coverage-v8` no está instalado y no se instaló nada. No hay `@testing-library` ni jsdom: los 18 `.tsx` no tienen tests.

### 4.7 build

`npm run build`: **PASA**, exit 0, 1.807 módulos, 1,04 s. Única advertencia de Vite: chunks mayores a 500 kB. Bundle principal `index-BAWzTLaT.js` **2.991 kB (841,8 kB gzip)**, un solo chunk sin división de código. Activos grandes embebidos: `node_index` 1.418 kB (201 kB gzip), `lines` 1.488 kB, `network` 729 kB, `substations` 715 kB, `plants` 638 kB, y 33 archivos woff2 (todos los subconjuntos de Roboto, incluidos cirílico y griego). `npm ci` instaló 178 paquetes en 4 s y reportó **11 vulnerabilidades (3 moderadas, 8 altas)** sin triaje.

### 4.8 Grafo de imports (regla hexagonal)

`scripts/metrics.py`, AST de todos los imports (incluidos los locales a función):

- **domain a infrastructure, api, application, mcp, cli o sim_fixtures: 0 violaciones.**
- Ciclos de import a nivel de módulo: **0**. Contando imports locales a función: 2 grupos.
  1. `application.build_regional` y `infrastructure.container`: `container.py:6` importa `build_regional` arriba y `build_regional.py:123` importa `container` dentro de una función.
  2. Seis módulos de `api` cerrados por `from cascadasen.api.app import create_app` en `api/agent_openapi.py:141`.
- Otras aristas que doblan la regla estricta: `application` a `infrastructure` 6 (`build_regional.py:123,128`, `grids.py:314-315`, `run_experiment.py:108`, `grid_health.py:15`), `infrastructure` a `application` 3 (`container.py:5-6`, `exporters.py:13`), `api` a `mcp` 4 (`api/assistant_routes.py:29-32`).
- E/S dentro del dominio: `domain/cascade/scenario.py:70`, `domain/simulation/params.py:66` y `domain/grids.py:44` leen archivos; `domain/unify.py:126` llama a `datetime.now` (solo metadato).

Matriz completa (filas importan columnas):

| De \ a | api | application | domain | infrastructure | mcp |
|---|---|---|---|---|---|
| api | - | 13 | 8 | 8 | 4 |
| application | 0 | - | 68 | 6 | 0 |
| domain | 0 | 0 | - | 0 | 0 |
| infrastructure | 0 | 3 | 22 | - | 0 |
| mcp | 0 | 0 | 3 | 0 | - |

### 4.9 Longitud y complejidad de funciones

Backend (`src`: 22.633 líneas en 118 archivos; `tests`: 5.912 líneas en 43):

- 1.070 funciones (AST). **51 superan 50 líneas, 11 superan 100.** Complejidad ciclomática (radon) sobre 10: **135 bloques**; sobre 20: 41; de 30 o más: 17. Distribución radon: A 1.015, B 159, C 94, D 25, E 8, F 8; media 4,63.
- Índice de mantenibilidad radon en grado C: `application/grid_queries.py`, `domain/unify.py`, `domain/theater/cycle.py`, `domain/regional_network.py`, `domain/theater/execution.py`.
- Archivos de más de 800 líneas: `domain/unify.py` 959, `domain/theater/cycle.py` 918, `api/session_routes.py` 854, `domain/regional_network.py` 806.

| Líneas | cc (radon; AST donde se indica) | Función | archivo:línea |
|---|---|---|---|
| 325 | 137 | `validate_snapshot` | `domain/validation.py:95` |
| 255 | 15 (AST) | `create_app` | `api/app.py:45` |
| 215 | 47 | `Simulation._cycle` | `domain/theater/cycle.py:489` |
| 187 | 54 | `apply_overlay` | `domain/cascade/overlay.py:193` |
| 180 | 80 | `infer_line_topology` | `domain/topology_inference.py:53` |
| 158 | 35 | `GridUnifier._reconcile_cen_sections` | `domain/unify.py:291` |
| 136 | 42 | `run_transient` | `domain/simulation/engine.py:398` |
| 111 | 46 | `GridUnifier._plants` | `domain/unify.py:616` |
| 84 | 43 | `build_flow_network` | `domain/regional_network.py:169` |

16 de las 20 funciones más complejas están en `domain/`. Atenuante: `validate_snapshot` es una lista plana de unos 20 bloques `checks.append(_check(...))` (alta cc por conteo de condiciones, no por anidamiento) y `create_app` es registro de rutas.

Frontend (856 funciones parseadas): una sola función de más de 80 líneas en código de aplicación, **`CascadeApp` con 530 líneas** (`web/src/cascade/CascadeApp.tsx:50`; el archivo tiene 604, 61 llamadas a hooks y 32 imports). Siguen `useSession` 77, `TimelineCard` 76, `buildCascadeLayers` 65. 156 líneas superan 160 caracteres (la mayor, 522, en `cascade/Legend.tsx:16`).

### 4.10 Excepciones silenciosas y supresiones (backend `src`)

81 handlers `except` (AST, `scripts/excepts.py`). 0 `except:` desnudo, 0 `except BaseException`, **0 `except ...: pass`**.

- `except Exception`: 11. Tres re-lanzan al menos en parte, nueve registran, **uno no hace ninguna de las dos cosas**: `application/assistant.py:66-67` (`except Exception: self.callback = None`, sin log).
- Handlers estrechos que solo retornan o continúan: 13, todos con tipos específicos (por ejemplo `application/sessions.py:207`, que forma parte del bucle de reintento y termina en `raise ConflictError` en `:211`; `FileNotFoundError` en los stores; `(TypeError, ValueError)` en los parsers de fuentes).
- **Cifra de cabecera: 14 manejadores silenciosos** (1 amplio sin log más 13 estrechos).
- `# type: ignore`: 6 (`api/session_routes.py:366,392`, `domain/grids.py:44`, `domain/regional_network.py:383`, `domain/simulation/network.py:133,137`). `# noqa`: 2. `print(`: 30 llamadas en 7 archivos, todas en CLI o reportes.

Frontend: 5 `try/catch` (2 vacíos con comentario: `map/baseMap.ts:79`, `session/sessionApi.ts:96`) y 5 `.catch(() => ...)` que descartan el error (`cascade/NetworkPanel.tsx:9`, `cascade/CascadeApp.tsx:180`, `cascade/gridsApi.ts:21`, `session/sessionApi.ts:43`, `session/useSession.ts:71`). No existe `ErrorBoundary` en `web/src`.

### 4.11 Otras mediciones

- Duplicación textual (pylint): 0 bloques de 10 líneas; 7 bloques de 5 a 13 líneas (por ejemplo `session_routes.py:780-788` con `simulation_routes.py:308-316`).
- Secretos: 0 coincidencias de `AKIA/ASIA`, clave PEM, `sk-`, `ghp_`, `xox`, `AIza` en árbol e historial (296 commits). `gitleaks` reporta 3 coincidencias, todas falsos positivos (`backend/README.md:85`, `defenses.yaml:29`, `operating_points.yaml:23`). El token Mapbox `pk.*` en `infrastructure/deploy.sh:20` es público y deliberado. Rutas locales reales (sin secreto): `docs/datasets.md:102`, `infrastructure/deploy.sh:13`.
- `git ls-files`: 2.227 rutas, 64,5 MB (`web/public` 39,8 MB, `data/processed` 21,2 MB). `.git` pesa 21 MB.
- Commits: 160 de 165 no-merge usan Conventional Commits; 149 de 165 tocan `CHANGELOG.md` (90 %).
- Determinismo: cabeza de auditoría idéntica para las políticas A y C con `PYTHONHASHSEED` = 0, 1 y 12345.

---

## 5. Fortalezas (con evidencia)

1. **Regla hexagonal en el dominio.** 0 imports de `domain` hacia capas externas y 0 ciclos a nivel de módulo (sección 4.8).
2. **El motor sigue la documentación.** Umbral de apertura 120 % y desempates en `domain/cascade/engine.py:241,243`; máximo 20 etapas en `:212`; ecuación de oscilación en `domain/cascade/frequency.py:147`; reserva, baterías, amortiguación y EDAC en `frequency.py:98-146`; regla de voltaje 1.600 / 1.000 MW en `engine.py:167` con pérdida de ambas islas por `reason: "voltage"` en `:287-288`. El reparto 1.905 / 287 MW de 25F está dentro de la banda del 15 % del test (`test_cascade.py:268-282`).
3. **Supuestos obligatorios.** `domain/simulation/params.py:47-48` lanza `ParameterError` si un valor no trae `source` ni `is_assumption`; `test_cascade.py:311-316` lo verifica sobre `cascade.yaml` (13 supuestos ahí, 59 en todos los YAML de parámetros). Cada línea de tiempo devuelve su lista `assumptions` (`engine.py:23-34`).
4. **Teatro determinista.** `domain/theater/rng.py:14-17` deriva flujos nombrados con SHA-256 a partir de la semilla; `new_seed()` usa `secrets` (`:20-22`) y la semilla se registra en la receta. Verificado con tres valores de `PYTHONHASHSEED` (sección 4.11). El reloj entra por parámetros `clock=` (`sessions.py:93`, `run_experiment.py:105`).
5. **Validación honesta.** `tests/validation/test_engine_cases.py` verifica V1 (reparto 1.800 / 314 MW, 15 %), V3a/V3b (frecuencia mínima y MW desconectados, 20 %), V4 (apagón a 4,6 ± 1 s), V5 (51,3 ± 0,3 Hz), V7, V8 y V10. V6 y V9 están marcadas `skip` con el motivo (`:96`, `:123`) y `backend/README.md` lo dice.
6. **Sesiones y límites.** `SessionLocks` acota esperas y libera entradas (`api/limits.py:72-107`, `max_waiters = 10` en `:80`); `SessionService.mutate` escribe con `If-Match` (`application/sessions.py:174-211`); topes de overlay (`domain/cascade/overlay.py:27-35`); ids con regex (`api/session_routes.py:112-123`); 5 tests del lock (`test_session_locks.py`) y pruebas 429 y 413 (`test_sessions_api.py:189-199,288-300`).
7. **Rutas de archivos seguras.** `infrastructure/grid_store.py:15-18` rechaza rutas absolutas, `..` y barras invertidas; `GET /grids/documents/{key}` solo sirve claves del manifiesto con sha256 (`application/grids.py:138-147`).
8. **Contratos probados.** `tests/integration/test_agent_openapi.py` falla si `docs/openapi/agents.openapi.json` se desvía de la app; `tests/unit/test_tool_specs.py` une las herramientas MCP y del asistente con la spec; las 31 rutas de sesión coinciden con las 31 filas de `docs/sessions-api.md:45-75`; no hay ruta documentada inexistente.
9. **Barreras de `docs/cyber.md` en código.** Sin herramienta de ranking, cortes de 1 a 3 líneas (`application/sessions.py:38`), MW solo desde las palabras del usuario (`mcp/toolbox.py:60-64`), `end_session` retenido, el adversario es código con semilla, la salida de herramientas se trata como datos (`api/assistant_routes.py:59-60`).
10. **Frontend con tipos reales.** 1 `: any` (`web/src/map/mapboxMap.ts:53`), 0 `as any`, 0 `@ts-ignore`, 0 `console.log`, 0 `innerHTML` ni `dangerouslySetInnerHTML`; los nombres libres de elementos se muestran como nodos de texto de React (`session/DataPanel.tsx:86,111`) y el DOM manual de `map/nodeDetail.ts` usa `textContent`.
11. **Cliente de sesión con diseño de concurrencia.** 409 con `Retry-After` se reintenta 2 veces con espera tope de 10 s (`session/sessionApi.ts:30-42`); 412 recarga, 404 vuelve al caso base y 409 ocupado reintenta cada 3 s (`session/useSession.ts:68-76`); el cargador descarta respuestas viejas por número de secuencia (`session/loader.ts:15-32`, con test).
12. **Scripts de datos reproducibles.** Reconstruí `node_index.json` en memoria y quedó idéntico al versionado (1.414.730 bytes); `build_baseline_opf.py` usa HiGHS con entradas y orden estables; los `.sh` fijan `mapshaper@0.8.6` y usan `set -euo pipefail` con `curl -fsSL`.
13. **Documentación de módulos.** 106 de 106 módulos del backend con docstring, y los mayores citan su sección de doc (`limits.py:1-4`, `engine.py:1`). 149 de 165 commits llevan entrada de changelog.
14. **Lint limpio y fijado.** ruff 0 hallazgos sobre 162 archivos; 6 `type: ignore`; 0 `TODO`.

---

## 6. Hallazgos por área

### 6.1 Backend dominio

| Id | Sev. | Archivo:línea | Evidencia | Corrección sugerida |
|---|---|---|---|---|
| **B-03** | media | `domain/simulation/frequency.py:102` y `domain/cascade/frequency.py:126` | Dos implementaciones de la ecuación de oscilación, reserva, batería, amortiguación y EDAC. V1-V10 validan el motor de 13 áreas (`domain/simulation`), no el de 188 barras que sirve el mapa, las sesiones y el teatro; en ese solo se prueba el reparto V1 (`test_cascade.py:268-282`). `docs/engine.md` lo dice, pero presentar "validado contra 25F" para el motor principal sería impreciso. | Corto plazo: una frase en el README y la UI (1 h). Mediano: portar V3-V5 al motor de 188 barras (16-24 h) o extraer un integrador compartido (8 h). |
| **B-06** | media | `domain/theater/execution.py:417-425`, `domain/theater/digital.py:157-159`, `domain/agents/stabilization.py:66,150` | Desde el PR #76 el motor devuelve `blackout` con `reason: "voltage"` (`engine.py:287-288`; `docs/engine.md:26`), pero el teatro sigue buscando el veredicto `voltage_limited`. Ningún módulo de `domain/cascade` ni `domain/simulation` lo produce, así que la alarma y el veto `stab_voltage_uncertain` solo se alcanzan con alarmas inyectadas en tests (`test_physical_bots.py:129`). | Decisión de comportamiento del equipo: mapear `reason == "voltage"` a `uncertain` en `execution.py` (restaura alarma y veto) o borrar la rama muerta y actualizar `docs/agents.md:46,56,83`, `docs/health.md:32` y `cascade.yaml:90-93`. 3 h. |
| **B-09** | media | `domain/validation.py:95`, `domain/theater/cycle.py:489`, `domain/topology_inference.py:53`, `domain/cascade/overlay.py:193`, `domain/simulation/engine.py:398`, `domain/unify.py:291,616` | Funciones de 111 a 325 líneas, cc radon 35 a 137 (tabla en 4.9). Radon grado C en 5 archivos. Atenuante: `validate_snapshot` es una lista plana de checks. | Una función por check en `validate_snapshot` (6 h); dividir `_cycle` en sus seis fases documentadas (8 h). |
| **B-16** | baja | `domain/cascade/engine.py:302`, `:289`, `:296`, `:418`; `domain/simulation/network.py` (`X_MIN_PU`) | `F0_HZ = 50.0` duplica `f0_hz` de `cascade.yaml:7`. Umbrales sueltos (`gen < 0.5`, `abs(gen-load) < 1.0`, `abs(f) >= 5`) fuera del cargador con proveniencia. `ASSUMPTIONS` (`engine.py:23-34`) repite en prosa números del YAML; hoy coinciden, nada los ata. | Mover las constantes a `cascade.yaml` y construir las frases desde los registros cargados. 3 h. |
| **B-07** | media | `domain/cascade/health.py:170-198`, `tests/unit/test_health.py:55-59` | `docs/cyber.md` 8.2 prohíbe buscar los elementos de mayor daño y mostrar rankings. `n1_margins` hace un barrido de corte simple sobre todas las líneas y reporta el peor con su id (`f"{worst:.0f} MW ({worst_id})"`). Es informativo, está fuera del índice (`in_index=False`) y solo es alcanzable por la CLI `cascadasen-health`; un test lo fija. Riesgo residual: `web/public/cache` publica el resultado de cada corte simple en 4 puntos de operación, así que un ranking es un orden de distancia (es el diseño "clic en cualquier línea"). | Quitar el id de `n1_worst` (informar solo la proporción) y agregar un test que verifique que ninguna salida de API o herramienta contiene un orden por elemento. 2 h. Es una decisión del equipo. |

### 6.2 Backend application / api / infrastructure

| Id | Sev. | Archivo:línea | Evidencia | Corrección sugerida |
|---|---|---|---|---|
| **B-04** | media | `api/limits.py:136-141`, `:19` | `BodyLimitMiddleware` solo lee la cabecera `content-length`; sin ella (transferencia chunked) la petición pasa. Prueba con `scripts/chunk.py`: un cuerpo de 300 KB con `Content-Length` da 413; el mismo cuerpo chunked llega a validación y devuelve 422. `docs/sessions-api.md` sección 8 promete "64 KB (413)". `BODY_LIMIT_PREFIXES` omite `/api/v1/sim/campaigns`, `/graph/islands`, `/simulate` y `/grids/*`. | Contar bytes en un `receive` envuelto y responder 413 al pasar el límite; agregar los prefijos. 2 h. |
| **B-05** | media | `api/simulation_routes.py:372-396`, `application/run_campaign.py:35` | `POST /api/v1/sim/campaigns` no declara `dependencies=RATE_LIMITED` (los endpoints de `:221,267,284,305` sí) y no tiene autenticación. Ejecuta hasta `MAX_RUNS = 240` simulaciones en un hilo. Medido (`scripts/camp.py`): 120 corridas tardaron 26,9 s en un portátil; el máximo ronda 55 s. CloudFront corta a los 30 s pero el servidor sigue calculando. | Aplicar el limitador global y bajar el tope (por ejemplo 60) o correr como tarea en segundo plano. 2 h. |
| **B-08** | media | `application/build_regional.py:123,128`, `application/grids.py:314-315`, `application/run_experiment.py:108`, `application/grid_health.py:15`, `infrastructure/exporters.py:13`, `api/agent_openapi.py:141` | Fugas de capa y 2 ciclos con imports locales (sección 4.8). Ningún test protege la regla. `backend/README.md` muestra solo `api -> application -> domain <- infrastructure`. | Pasar el `container` a `build_regional`; test de reglas de import o contrato `import-linter` en CI. 6-8 h (el test solo, 1 h). |
| **B-20** | baja | `api/simulation_routes.py:221-356` y `api/session_routes.py:630-850` | `/sim/runs*` (10 operaciones de agente) y `/sessions/{sid}/runs*` (10) exponen los mismos comandos. `docs/openapi.md` dice que los globales "stay marked until sessions exist"; las sesiones ya existen. | Marcar como deprecado el conjunto global en la spec. 3 h. |
| **B-11** | baja | `application/assistant.py:66-67` | Único `except Exception` que no registra ni re-lanza: la devolución de llamada del stream se descarta sin rastro. La intención es válida (un cliente que se fue no debe detener la conversación) pero merece un log a nivel debug. El resto de los 13 handlers estrechos son legítimos (sección 4.10). | Agregar `log.debug(...)`. 0,25 h. |
| **B-13** | baja | `application/theater_world.py:31`, `domain/agents/logistics.py:75`, `domain/simulation/grid.py:128,147`, `domain/theater/decisions.py:26,85`, `domain/theater/execution.py:78`, `domain/theater/grid.py:163,432`, `api/static/map.html` | 11 métodos sin llamador en `src` ni `tests` (`vulture --min-confidence 60` y `grep`). `api/static/map.html` (54.864 bytes) es una página de prueba heredada que se sirve en `/map`. | Eliminar. 1 h. |
| **B-19** | baja | `api/app.py:62-68`, `application/sessions.py:143` | CORS `allow_origins=["*"]` con cabeceras abiertas. Sin cookies ni credenciales y con el id de sesión como capacidad (128 bits, `secrets.token_urlsafe(16)`), es coherente con el diseño documentado (`sessions-api.md` sección 1). El autor de una edición (`X-Sub50-Agent`) es autodeclarado. Los ids de corrida globales tienen 48 bits (`uuid4().hex[:12]`, `run_experiment.py:163`). | Ninguna para el hackatón; si la API pasa a ser pública, restringir CORS al origen web. |
| **R-05** | media | `infrastructure/sources/{ide_energia,pypsa_cl,infotecnica,ine_censo}.py`, `infrastructure/http.py`, `application/cache_builder.py`, `backend/pyproject.toml:46-48` | 12 módulos bajo 50 % de cobertura (sección 4.4). Los cuatro adaptadores parsean las fuentes de las que depende toda la red unificada. `pyproject.toml` no define `--cov` por defecto ni `fail_under`. | Fixtures de respuestas grabadas para los cuatro adaptadores y `CachedHttp` (6 h); `addopts` con cobertura y `fail_under` (0,5 h). |

Ver también: R-03 (mypy), en 6.6.

### 6.3 MCP / asistente

| Id | Sev. | Archivo:línea | Evidencia | Corrección sugerida |
|---|---|---|---|---|
| **B-17** | media | `api/assistant_routes.py:138-143` y `infrastructure/settings.py:33-36` | `POST /assistant/chat` y `/chat/stream` están abiertos y llaman a un modelo de pago en Bedrock. La única cota es 10 mensajes por minuto por IP, 8 pasos por mensaje (`settings.py:33`) y `maxTokens` 2000. `docs/assistant.md` sección 4 lo declara y `plan.md` sección 9 lista el tope diario como decisión abierta. Un atacante con muchas IPs no queda acotado. | Presupuesto diario global de tokens o mensajes en el document store y un interruptor `ASSISTANT_ENABLED`. 4 h. |
| **B-18** | baja | `application/assistant.py:30-46` | `announces()` decide si empujar al modelo con una lista de regex en futuro español: probado (`test_assistant.py:211-239`) pero frágil al idioma. Nombres de barra y elementos son texto libre de hasta 80 caracteres (`api/session_schemas.py:34,40,50`) que llega al modelo vía resultados de herramientas; hay mitigaciones (instrucción de tratar la salida como datos, herramientas acotadas a una sesión, `step` tope 24) pero ningún test envía un nombre inyectado. El banco que probó la inyección "no está en el repo" (`docs/assistant.md` sección 5). | Un test con un nombre de elemento inyectado y guardar el banco en `backend/tests/bench/`. 3 h. |
| **B-12** | baja | `tests/unit/test_llm_commander.py:128-130`, `tests/integration/test_mcp_server.py:9`, `tests/unit/test_mcp_tools.py:6`, `backend/pyproject.toml:29-34` | `import anthropic` sin `importorskip` rompe `uv run pytest` por defecto. Los extras `mcp` y `llm` no están en el grupo `dev`, por lo que `mcp/server.py` queda en 0 % y dos archivos de tests se omiten. | `pytest.importorskip("anthropic")` y poner ambos extras en `dev` o correrlos en CI. 1 h. |

Ver también: B-07 (barrera por nombre, `tests/unit/test_mcp_tools.py:153-157`), B-08 (`api` importa cuatro módulos de `mcp/`, la capa compartida de herramientas vive en un paquete con nombre de cliente).

### 6.4 Frontend

| Id | Sev. | Archivo:línea | Evidencia | Corrección sugerida |
|---|---|---|---|---|
| **W-01** | media | `web/src/cascade/CascadeApp.tsx:50-590` | Un componente de 530 líneas, 61 hooks y 32 imports. Maneja URL (`:56,139`), sesión (`:57,133-135`), carga de línea de tiempo y guarda de obsolescencia (`:127,174-203`), un bucle `requestAnimationFrame` que llama a `setT` en cada cuadro (`:296-320`), tooltips con CSS en línea (`:248-270`) y el JSX completo. 14 `useEffect` con arreglos de dependencias que omiten lo que leen (`:131-140`); funciona porque lo omitido deriva de lo listado, pero nada lo verifica (no hay eslint). Un ref `live` copia 16 valores por render. Sin test. | Extraer `useTimelinePlayback`, `useScenarioLoader`, `buildTooltip` a `cascade/tooltip.ts` y el rail a `Rail.tsx`. Objetivo bajo 250 líneas. 10 h, sin cambio de comportamiento. |
| **W-04** | media | los 18 `.tsx`; `web/src/session/useSession.ts:60-94` | 13 archivos de test, todos sobre `.ts` de lógica. Sin `@testing-library` ni jsdom. `useSession.ts`, la máquina de estados 412/409/404, no tiene test, mientras que sus partes puras (`sessionApi`, `loader`) sí. 32 de 45 módulos sin test hermano. Cobertura no medida. | `happy-dom` y `@testing-library/react`; probar `useSession` y un render de humo de `DataPanel` y `CascadeApp` con `fetch` simulado. 8 h. |
| **W-05** | media | `web/src/map/nodeDetail.ts:159-160`, `web/src/cascade/Scenarios.tsx:7`, `web/src/cascade/url.ts:4`, `web/src/cascade/text.ts:4-8,63`, `web/src/cascade/NetworkState.tsx:58,74,79-81`, `web/src/cascade/layers.ts:19-25`, `web/src/map/layers.ts:8-14`, `web/src/map/{chileMap,baseMap,mapboxMap}.ts` | Constantes y tipos copiados a mano del backend, sin contrato generado: punto por defecto `nov2026-1300` (también `application/sessions.py:35`), caso 25F, regex del id de sesión (`sessionApi.ts:6`), umbrales "120 %" y "47,5 Hz" solo en texto frente a `physics.yaml:8,33`, razones de falla de isla en dos mapas con redacción distinta, tecnologías en 3 archivos web y 3 del backend, dos tablas de tensión inconsistentes dentro de la web, `SEN_BOUNDS` triplicada. Los tipos de sesión coinciden hoy con `api/session_schemas.py:195-258`, pero el backend declara muchas salidas anidadas como `dict[str, Any]` (`:207,212,232,242-255`), así que la deriva no es detectable por máquina. | Servir umbrales y etiquetas en `index.json` (8 h); generar tipos TS desde `docs/openapi/agents.openapi.json` y dar modelos reales a las salidas `dict[str, Any]` (8 h). |
| **W-06** | baja | `web/src/session/sessionApi.ts:30-44`, `web/src/session/useSession.ts:6` | `BUSY_RETRIES = 2` y `BUSY_RELOAD_MS = 3000` están afinados al servidor (`max_waiters = 10`, `Retry-After: 1`); el acoplamiento solo está documentado. Un 429 con `Retry-After` se muestra como error genérico (sin rama 429) y las esperas de reintento no son cancelables (sin `AbortController`). | Leer `Retry-After` también para 429 y aceptar un `AbortSignal`. 2 h. |
| **W-07** | baja | `web/src/main.tsx:9-18`, `web/src/App.tsx`, `web/src/Legend.tsx`, `web/src/map/{chileMap,mapboxMap}.ts`, `web/src/cascade/icons.ts` | `?mapa=1` y `?mapa=2` están "deprecated, kept for reference" pero siguen en el único bundle de 2,99 MB. Arrastran `: any` (`mapboxMap.ts:53`), `fetch(...).then((r) => r.json())` sin chequear `r.ok` (`map/nodeDetail.ts:60`) y un segundo `Legend`. `cascade/icons.ts` (65 líneas, 12 PNG) no tiene importadores (`docs/mapa3.md:129` lo declara vacío por ahora). Unas 11 funciones de corridas de `sessionApi.ts` (`:51,64-74`) nunca se llaman desde la UI. | Borrar mapas 1 y 2 (están en el historial) o `React.lazy`; dividir el chunk de deck.gl y mapbox. 3 h a 5 h. |
| **W-08** | baja | `web/src/session/sessionApi.ts:96`, `web/src/cascade/CascadeApp.tsx:130,180`, `web/src/cascade/NetworkPanel.tsx:9`, `web/src/session/useSession.ts:71`, `web/src/map/baseMap.ts:79` | 5 sitios descartan el error sin log. La misma llamada `loadRegionalGrid` registra en `:130` y calla en `:180`. Sin `ErrorBoundary`, una excepción de render deja la app en blanco. | Un `<ErrorBoundary>` alrededor de `CascadeApp` con mensaje en español y botón de recarga, y `console.warn` en los sitios mudos. 1,5 h. |
| **W-09** | baja | `web/src/cascade/Legend.tsx:16,75`, `web/src/cascade/ui.tsx:56`, `web/src/session/DataPanel.tsx:65`, `web/src/cascade/SimulationPanel.tsx:56,73`, `web/src/cascade/CascadeApp.tsx:255` | 156 líneas de más de 160 caracteres (máximo 522) y 17 sitios con `style={{`. Sin prettier. | Prettier con `printWidth: 140`, una pasada mecánica. 2 h. |
| **W-12** | baja | `web/package.json`, `web/package-lock.json` | `npm ci` reporta 11 vulnerabilidades (3 moderadas, 8 altas), sin triaje; el build copia 33 woff2 (todos los subconjuntos de Roboto). | `npm audit` y registrar el resultado; importar solo el subconjunto latino. 2 h. |

Observación informativa (W-11): hoy no hay UI del asistente en `web/src` de este commit (`docs/assistant.md:122` la lista como no construida). `upstream/main` la agrega; al revisarla hay que confirmar que la respuesta se renderiza como texto.

Ver también: R-04 (sin lint ni CI para `web/`), R-09 (symlink `node_modules`).

### 6.5 Scripts de datos

| Id | Sev. | Archivo:línea | Evidencia | Corrección sugerida |
|---|---|---|---|---|
| **D-01** | media | `data/scripts/build_operating_points.py:143-155` | `_ensure_loads_file()` ejecuta el `curl` de la página de SharePoint en cada corrida aunque los cuatro `.xlsx` existan, así que una reconstrucción falla sin red. Las descargas usan `curl -sL` sin `-f` (`:148,154`): un error HTTP se guarda como `.xlsx` (HTML), la siguiente corrida lo ve existente y `openpyxl` falla con un mensaje confuso. Sin checksum. Los `.sh` hermanos usan `curl -fsSL` y el pipeline Python tiene `CachedHttp` (`infrastructure/http.py`), de modo que la lógica existe dos veces. | Omitir la petición de cookies si los archivos existen, usar `-f` o `CachedHttp`, y registrar sha256 de cada entrada (ver D-03). 3 h. |
| **D-02** | media | `data/scripts/*.py`, `.github/workflows/lint.yml:19-23`, `scripts/lint.sh` | Los 761 líneas de Python de `data/scripts` quedan fuera de ruff en CI (corre con `working-directory: backend`) y de cualquier test. Los únicos chequeos son los `assert` al final de cada script. El motor lee las tres salidas (`operating_points.json`, `baseline_opf.json`, `node_index.json`), así que una mala construcción se detecta de forma indirecta, no la lógica del script (`_commit_for_inertia`, `_dispatch`, `_plants_to_buses`). | `ruff check ../data/scripts` en CI (0,5 h) y un test con una instantánea sintética pequeña (4 h). |
| **D-03** | media | `data/scripts/build_baseline_opf.py:48-57,205-214`, `data/scripts/build_node_index.py:186-194` | `docs/datasets.md` sección 6 exige `source` o `is_assumption` en todo número de la UI. `operating_points.json` lo cumple; `baseline_opf.json` no trae `source`, `assumptions` ni hashes de entrada (y `SHED_COST = 5000`, `CAPACITY_FACTOR = 1.0` solo están en código); `node_index.json` no tiene cabecera. Ninguno guarda commit, hashes ni fecha de descarga de PyPSA-CL, y la carpeta de SharePoint es mutable. | `source`, `assumptions` e `inputs: {archivo: sha256}` en la cabecera, o un `data/processed/MANIFEST.json`. 3 h. |
| **R-23** | media | `data/scripts/build_baseline_opf.py:20-22`, `backend/pyproject.toml` | Importa `scipy.optimize` y `scipy.sparse`; `scipy` no aparece en `pyproject.toml` ni en `uv.lock` (0 coincidencias), así que `uv sync` no lo instala. `docs/mapa3.md:231` lo admite ("needs `openpyxl` and `scipy`, not in the repo dependencies"). | Grupo de dependencias `data` con scipy y openpyxl. 0,25 h. |
| **D-04** | baja | `data/scripts/build_baseline_opf.py:20-29,60-70`, `data/scripts/build_operating_points.py:271-279` | El script OPF agrega `backend/src` a `sys.path` y carga `build_operating_points.py` por ruta para llamar a funciones con guion bajo. La regla de inercia está implementada dos veces (`_commit_for_inertia`, `_committed`). | Módulo compartido o convertir los scripts en un paquete bajo `application/`. 4 h. |
| **D-05** | baja | `data/scripts/build_node_index.py:180-185`, `data/scripts/build_operating_points.py:337` | Autochequeos con `assert` (se eliminan con `python -O`) y números mágicos del dato actual (20 líneas y 10 plantas en la subestación Alto Jahuel; 259 cargas; más de 3.000 registros de línea). Una actualización legítima de datos los rompe. | `raise SystemExit` con tolerancias, o un test con la versión del dato. 1 h. |
| **D-06** | baja | `docs/datasets.md:102,141,186`, `docs/datasets.md:220` | El Anexo A apunta a `data/scripts/descargar_centrales.py` (no existe; `git ls-files data/scripts` lista 5 archivos). `:102` cita rutas en la máquina de un desarrollador. `:141` aún dice "The engine has about 10-14 nodes" (la red es de 188 barras). Las secciones 2-5 están marcadas "original research notes". | Borrar o marcar el anexo. 0,5 h. |
| **D-07** | baja | `data/processed/` (29 archivos) | Se versiona a propósito (entrada de tests e imagen). `atlas_sen.html` (4,4 MB) es una salida de build. La licencia de PyPSA-CL figura "not stated" (`docs/datasets.md`) y la de Chile-GeoJSON "no license file" (`build_chile_outline.sh:3`) mientras se redistribuyen en un repo público. | `data/README.md` con la licencia de cada archivo. 1 h. |

### 6.6 Tests y CI

| Id | Sev. | Archivo:línea | Evidencia | Corrección sugerida |
|---|---|---|---|---|
| **R-01** (también B-02, W-03) | **alta** | `.github/workflows/lint.yml`, `.github/workflows/deploy.yml:6-9` | `lint.yml` tiene dos trabajos: `ruff` (`ruff check` y `ruff format --check` en `backend/`) y `changelog` (solo en `pull_request`). `deploy.yml` se dispara en cada push a `main` y no depende de ningún trabajo de pruebas. No corren pytest, vitest, `tsc` aparte, mypy, cobertura ni eslint. `docs/plan.md:16,38` promete "validation tests running in CI". Los 3 fallos de R-02 llegaron a `main` por esto. El issue #79 lo llama el arreglo más barato de mayor efecto. | Trabajo `backend-test` (`uv sync --group dev`, `uv run pytest -q --cov=cascadasen --cov-fail-under=85`, 2 h); trabajo `web` (`npm ci`, `npx tsc --noEmit`, `npx vitest run`, `npm run build`, 1,5 h); `deploy` con `needs:` de ambos (0,5 h). 4 h, y requiere R-02 antes. |
| **R-02** (también B-01, B-12) | media | `backend/tests/unit/test_grid_simulation.py:80-84`, `backend/tests/unit/test_llm_commander.py:128-130`, `domain/cascade/engine.py:417` | 3 tests en rojo en `main` (sección 4.4). Dos por deriva de la caché versionada contra el motor en el límite exacto de 100 % de carga; uno por `import anthropic` sin `importorskip`. Posible corrección upstream: `a128793` regeneró la caché y modificó el test. | `pytest.importorskip("anthropic")` (0,25 h). Para la caché: tolerancia en `status` cuando `loading == 1.0` o `ratio > 1.0 + 1e-6`, y regenerar con `cascadasen-cache` (3 h). |
| **R-03** (también B-10) | media | `backend/pyproject.toml` (sin `[tool.mypy]`) | 179 errores en 33 de 118 archivos; 163 en código. El issue #79 sección 3 pide "mypy runs without errors or the remaining errors are noted". | `[tool.mypy]` con `ignore_missing_imports` y un baseline en CI (2 h); corregir los 163 empezando por `unify.py`, `validation.py`, `theater/execution.py`, `session_schemas.py` (hasta 12 h). |
| **R-04** (también W-03, D-02) | media | `scripts/lint.sh:9,31-32,63`, `AGENTS.md:30`, `web/package.json` | `lint.sh` solo maneja `$ROOT/frontend/*`, directorio que no existe (la app está en `web/`), así que el hook de pre-commit y el hook de Claude omiten todo `web/`. Sin script `lint` ni eslint/prettier. `data/scripts` fuera de ruff (D-02). | Cambiar `frontend` por `web` en `lint.sh` y `AGENTS.md:30`; eslint con `react-hooks/exhaustive-deps` y prettier. 4 h más 3 h para lo que eslint reporte. |
| **R-06** | baja | `scripts/hooks/pre-commit:16`, `.github/workflows/lint.yml:26` | `mapfile` es un builtin de bash 4. Con `/bin/bash` 3.2.57 (el único `bash` de esta máquina) imprime "mapfile: command not found" y el hook falla, así que todo commit se rechaza salvo que un bash más nuevo esté primero en `PATH`. Además, el trabajo `changelog` solo corre en `pull_request`: 16 de 165 commits no-merge no tienen entrada. | Reemplazar `mapfile` por un bucle `while IFS= read -r`. 0,25 h. |
| **R-07** | baja | `backend/tests/unit/test_session_locks.py:63-70`, `backend/tests/integration/test_sessions_api.py:244-247,305-320`, `backend/tests/integration/test_assistant_api.py:244-248` | `while locks._locks["a"][1] < 2: time.sleep(0.01)` no tiene plazo (una regresión cuelga la suite); hay cotas de tiempo de reloj y `time.sleep(0.3)` que dependen del planificador. El test SSE sí acota su espera (200 × 5 ms). | Plazo en el bucle y `threading.Event`. 1 h. |
| **R-08** | baja | `backend/tests/validation/test_engine_cases.py:96,123`, `docs/plan.md:97,107` | `plan.md:97` declara V6 "must pass before demo" y su clasificación "verified", pero el test está en `skip`. `plan.md:107` promete que CI escribe la tabla "ours / published / source / pass" en el README; la tabla de `backend/README.md` es manual. Solo V7 corre como prueba independiente. | Reescribir `plan.md:97` como "no hecho" (0,5 h) o conseguir la clasificación del CEN. |

### 6.7 Documentación del código

| Id | Sev. | Archivo:línea | Evidencia | Corrección sugerida |
|---|---|---|---|---|
| **R-14** | **alta** | `README.md:1-49` | Es la plantilla del hackatón: lista el equipo y la checklist "Before Submitting" con tildes y la instrucción del emoji de banana (`:25`). 0 menciones de Sub50 o CascadaSEN. No explica qué es el producto, cómo correrlo ni cómo se validó, que es lo que el issue #79 sección 6 pide, y la nota sobre el nombre Sub50 / `cascadasen` solo está en `backend/README.md:3` y `docs/idea.md:3`. | README de unas 40 líneas: qué es, captura, `docker compose up --build`, enlace a `docs/docker.md`, resumen de validación, nota del nombre, mapa de docs. 1,5 h. |
| **R-15** | media | ver sección 7 | 26 puntos de documentación que contradicen el código, los peores en `docs/stack.md:3,7,9` y `docs/plan.md:8`. `AGENTS.md` 1.4 exige corregir el doc en el mismo cambio. | Reescribir cabeceras y la tabla de decisiones de `stack.md`, actualizar `plan.md` sección 0 y renumerar duplicados. 3 h. |
| **R-16** | media | `domain/unify.py`, `domain/validation.py:95`, `domain/theater/cycle.py:489`, `domain/topology_inference.py:53` | 205 de 824 funciones (25 %) y 75 de 296 clases (25 %) con docstring; 55 funciones de 40 o más líneas sin ninguna. `domain/unify.py` (959 líneas) tiene 12 líneas de comentario y 8 funciones de 40 o más líneas sin docstring; `_plants` (`:616`, 111 líneas, cc 46) encadena tres estrategias de emparejamiento sin una frase sobre su orden ni umbrales. Comentarios más docstrings suman 5 % de las líneas (radon). Atenuante: los módulos siempre tienen docstring y el motor se explica paso a paso en `docs/engine.md`. | Docstring con el porqué en las 15 funciones mayores. 3 h. |
| **B-14** | baja | `docs/stack.md` sección 7.1, `backend/README.md` "Main endpoints", `docs/architecture.md:27` | La tabla 7.1 omite `GET /sim/runs/{id}/snapshots`; el README omite `GET /api/v1/stats`, `/health`, `/simulate`, `/simulate/network`, `/grids/*`; `architecture.md:27` dice "no wall clock in the domain" pero `domain/unify.py:126` llama a `datetime.now`. | 2 h (incluye W-10 y D-06). |
| **R-19** (también W-10) | baja | `web/README.md:3`, `docs/mapa3.md:201-238,251,263` | `web/README.md:3` dice que la app "contains no physics" y que lee `data/processed/`; el mapa 3 lee `web/public/cache/` y la API. La tabla de archivos de `mapa3.md` sección 8 omite 11 módulos de `web/src/cascade`. Hay dos secciones "## 10" (`:251`, `:263`). | 0,75 h. |
| **R-10** | baja | `backend/README.md:104`, `backend/src/cascadasen/sim_fixtures.py:4`, `docs/mapa3.md:269`, `docs/architecture.md:91` | Los cuatro dicen que `web/public/cache/theater/` está git-ignored, pero ni `.gitignore` ni `web/.gitignore` tienen la regla (0 coincidencias de `theater`); `mapa3.md:269` agrega "like the cut cache", y esa caché sí está versionada. Nada en `web/src` lee `cache/theater/`. | Agregar la regla a `.gitignore` y corregir las frases, o eliminar el comando. 0,5 h. |
| **R-17** | baja | `CHANGELOG.md` | 165 entradas (194.532 bytes) para 165 commits no-merge; 149 tocan el archivo. Faltan entradas en, por ejemplo, `bdf0858`, `dda2fff`, `214ff59`, `cdc2ba0`, `32f6d0b`, `6bc580a`. A ese tamaño es pesado para un agente que lo lee entero. | Archivar entradas viejas en `CHANGELOG-archive.md` si importa. 0,5 h. |
| **R-18** | baja | `docs/adr/` (no existe) | El issue #79 sección 2 pregunta por `docs/adr/`. Las razones están en `plan.md` sección 9 y en los "Why" del changelog, pero dispersas. Candidatos: dos motores, capas y excepciones, caché versionada, sesiones por URL sin clave, CORS `*`. | 4 ADR cortos. 3 h. |

### 6.8 Modularidad

| Id | Sev. | Archivo:línea | Evidencia | Corrección sugerida |
|---|---|---|---|---|
| **R-20** (B-09, W-01) | media | ver 6.1 y 6.4; `api/app.py:101-299`, `application/grid_queries.py:144,488` | 51 funciones sobre 50 líneas, 17 bloques radon de cc 30 o más, 5 archivos en grado C. `create_app` (`api/app.py:45`) registra unas 20 rutas de consulta de red en línea mientras que grids, sesiones, simulación y asistente tienen su router. | Mover las rutas en línea a `api/grid_query_routes.py` (3 h, primer paso barato), más B-09 (hasta 17 h) y W-01 (10 h). |
| **R-21** (B-08) | media | ver 6.2; `api/assistant_routes.py:29-32` | La capa de herramientas compartida (`mcp/{client,state,toolbox,tools,specs,digest}`) vive en un paquete con nombre de un cliente y la importa `api`. | Moverla a un paquete neutro (por ejemplo `agent_tools/`) y convertir `scripts/metrics.py` (unas 60 líneas) en un test que verifique "domain no importa nada externo" y "sin ciclos a nivel de módulo". 6-8 h; el test solo, 1 h. |
| **R-22** (B-03, W-05) | media | ver 6.1 y 6.4 | Modelado duplicado (dos motores de frecuencia) y constantes duplicadas entre `web/` y `backend/`. La duplicación textual es baja, así que es duplicación de modelo, no copiar y pegar. | Ver B-03 y W-05. |
| **R-24** (W-07, B-13) | baja | ver 6.2 y 6.4 | Código muerto y heredado: `cascade/icons.ts`, mapas 1 y 2, 11 métodos sin llamador, `api/static/map.html`. | 1 h backend más 3 a 5 h web. |

### 6.9 Higiene del repositorio (transversal)

| Id | Sev. | Archivo:línea | Evidencia | Corrección sugerida |
|---|---|---|---|---|
| **R-09** (también B-15, W-02) | media | `web/node_modules` (modo 120000), `.gitignore:18` | `git ls-tree HEAD web/node_modules` da un symlink (blob `8a62e47`, commit `cf013db`) hacia `/Users/fsanhueza/Documents/GitHub/Hackaton/platanus-hack-26-cl-team-9/web/node_modules`, ruta de otra máquina. `.gitignore:18` es `node_modules/` (con barra) y no cubre un symlink ya versionado. `npm ci` lo reemplaza por un directorio real y deja `git status` en ` D web/node_modules`. **Corregido upstream** en `965c0a3` (`git ls-tree upstream/main web/node_modules` está vacío). | Mergear upstream; si no, `git rm --cached web/node_modules` e ignorar `node_modules` sin barra. 0,25 h. |
| **R-11** | baja | `.gitignore` | `git check-ignore --no-index backend/.coverage` no devuelve nada; `pytest-cov` está en el grupo `dev`, así que `pytest --cov` deja `backend/.coverage` sin ignorar (ocurrió en esta auditoría). | Agregar `.coverage`, `htmlcov/`, `web/coverage/`. 0,1 h. |
| **R-12** | baja | `data/processed/atlas_sen.html`, `data/processed/grid_snapshot.json`, `web/public/cache/**` | 39,8 MB y 1.855 archivos en `web/public/cache` versionados a propósito (la imagen desplegada no tiene Python, `web/README.md` "Mapa 3"), pero nada verifica que coincidan con el motor (R-02). | Que el test de caché corra en CI (parte de R-01). |
| **R-13** | baja | `docs/datasets.md:102`, `infrastructure/deploy.sh:13` | Rutas `/Users/alonsoutreras/...` en un doc y un script. Sin valor secreto. `deploy.sh` está fuera de alcance. | Reemplazar por `~/`. 0,25 h. |

---

## 7. Documentación obsoleta

Formato: doc:línea, qué dice, verdad del código.

| # | Doc:línea | Dice | Verdad del código |
|---|---|---|---|
| 1 | `README.md:1-49` | README de la plantilla | Sin contenido de Sub50 (R-14) |
| 2 | `docs/stack.md:3` | "Not implemented: the cascade engine, the timeline player and the fixtures in section 6" | Motor, reproductor y sesiones existen (`domain/cascade/engine.py`, `web/src/cascade/Timeline.tsx`, 31 rutas de sesión) |
| 3 | `docs/stack.md:7` | "The first MVPs are frontend only ... hand-written `network.json` and `timeline.json` ... no physics and no server" | Backend con 77 operaciones de API; la web lee la caché del motor y la API |
| 4 | `docs/stack.md:9` | "Backend work (simulation engine, API, cache builder, CI) is backlog" | Motor, API y `cascadasen-cache` existen; falta pruebas en CI |
| 5 | `docs/stack.md:27-30,35` (tabla de decisiones) | Motor, API, precómputo, LLM y pytest "Backlog"; Estado: Zustand; gráficos: uPlot | `web/package.json` no tiene `zustand` ni `uplot`; motor, API, `cascadasen-cache`, asistente y pytest existen |
| 6 | `docs/stack.md:45,48,173` | `build_cache.py`; `data/processed/network.json` | El comando es `cascadasen-cache` (`application/cache_builder.py`); el archivo es `sen_network.json` |
| 7 | `docs/stack.md` sección 7.1 | 13 operaciones de simulación | Son 14; falta `GET /sim/runs/{id}/snapshots` |
| 8 | `docs/plan.md:8` | "No cascade engine, player or fixtures yet" | Construidos |
| 9 | `docs/plan.md:16,38,107` | "validation tests running in CI", "CI that runs pytest and Vitest", "CI renders ... into the README" | Ningún workflow corre pruebas (R-01) |
| 10 | `docs/plan.md:62` | `scripts/build_cache.py` | `uv run cascadasen-cache` |
| 11 | `docs/plan.md:97` | V6 "must pass before demo", clasificación "verified" | `tests/validation/test_engine_cases.py:96` en `skip` |
| 12 | `docs/plan.md:149,151` | Dos ítems numerados "14." | Error de numeración |
| 13 | `docs/mapa3.md:251,263` | Dos secciones "## 10" | Error de numeración |
| 14 | `docs/mapa3.md:269`, `backend/README.md:104`, `backend/src/cascadasen/sim_fixtures.py:4` | `web/public/cache/theater/` git-ignored "like the cut cache" | Sin regla de ignore; la caché de cortes sí está versionada (R-10) |
| 15 | `docs/mapa3.md:201-238` | Lista de archivos de `web/src/cascade` | Omite 11 módulos (R-19) |
| 16 | `web/README.md:3` | La app "contains no physics"; los números vienen de `data/processed/` | Lee `web/public/cache/` y `/api` en modo sesión |
| 17 | `docs/architecture.md:27` | "no wall clock in the domain" | `domain/unify.py:126` llama a `datetime.now(UTC)` (solo metadato) |
| 18 | `docs/agents.md:46,56,83`, `docs/health.md:32`, `domain/cascade/params/cascade.yaml:90-93`, `domain/theater/execution.py:416-417` | Veredicto de isla `voltage_limited` / `uncertain` | `engine.py:287-288` devuelve `blackout` con `reason: voltage` (PR #76; `docs/engine.md:26`); la alarma y el veto son inalcanzables (B-06) |
| 19 | `docs/datasets.md:186,220` | `data/scripts/descargar_centrales.py`, `unificar_centrales.py` | No existen en el repo (secciones marcadas "original research notes") |
| 20 | `docs/datasets.md:102,141` | Archivos de plantas bajo `/Users/alonsoutreras/...`; "The engine has about 10-14 nodes" | Ruta de una máquina local; la red es de 188 barras (`docs/plan.md` decisión 4) |
| 21 | `docs/infrastructure.md:86` | `scripts/issue.sh` | El archivo no existe (el doc lo admite) |
| 22 | `docs/design.md:121` | `genzoom.py`, `genlevels.py` | No están en el repo (el doc lo admite) |
| 23 | `backend/README.md` "Main endpoints" | Lista de rutas de solo lectura | Omite `GET /api/v1/stats`, `/health`, `/simulate`, `/simulate/network`, `/grids/*` (B-14) |
| 24 | `AGENTS.md:30`, `scripts/lint.sh:9,31,63` | El frontend vive en `frontend/` | La app está en `web/` (R-04) |
| 25 | `docs/idea.md` §3.2, `docs/plan.md:37,139` | Pestaña "Qué lo habría evitado", tabla de validación, selectores de modo de defensa y causa, "10-14 nodos" | Ambas pestañas son botones deshabilitados (`web/src/cascade/CascadeApp.tsx:36,476`); sin selectores de modo de defensa ni causa; la red es de 188 barras |
| 26 | `project-description.md`, `platanus-hack-project.jsonc` | "agents attack and defend live", "discover which points are most fragile" | Decisión abierta 11 de `plan.md` sección 9; choca con `docs/cyber.md` sección 8 (sin ranking de puntos débiles) |

Vigentes y verificadas: `docs/sessions-api.md` (rutas, límites, ids), `docs/openapi.md`, `docs/assistant.md` (rutas), `docs/grids.md:22-28`, `docs/engine.md` (pasos), `docs/regional.md`, `docs/network-format.md`.

Posible corrección upstream: `docs/stack.md` y `docs/plan.md` cambian en `upstream/main`; no verifiqué si arreglan las filas 2 a 9.

---

## 8. Plan de correcciones priorizado

Impacto: variación estimada del puntaje del área afectada (y del global cuando es relevante). Costo en horas, estimación gruesa. "Issue propio" indica si conviene abrir un issue separado.

| # | Corrección | Hallazgos | Impacto estimado | Horas | ¿Issue propio? |
|---|---|---|---|---|---|
| 1 | Suite en verde: `importorskip("anthropic")` y tolerancia de `status` en `loading == 1.0` más regenerar la caché | R-02, B-01, B-12 | Tests y CI +0,5; prerrequisito de la fila 2 | 3,5 | Sí (junto con la 2) |
| 2 | CI con pytest (cobertura mínima), vitest, `tsc` y build, y `deploy` con `needs:` | R-01, B-02, W-03 | Tests y CI +1,0; global +0,2 | 4 | Sí |
| 3 | README raíz del producto | R-14 | Documentación +0,5 | 1,5 | Sí (el issue #79 lo pide) |
| 4 | Cabeceras y tablas obsoletas de `stack.md`, `plan.md`, `web/README.md`, `datasets.md` | R-15, B-14, W-10, D-06, R-19 | Documentación +0,25 | 3 a 4 | Sí, agrupado con la fila 3 |
| 5 | Quitar symlink `node_modules`, ignorar `.coverage`, regla `cache/theater`, `mapfile` del hook | R-09, R-11, R-10, R-06 | Higiene; evita ruido en `git status` | 0,6 | No (la 9 la resuelve el merge de upstream) |
| 6 | `lint.sh` y `AGENTS.md` hacia `web/`, ruff sobre `data/scripts`, eslint con `react-hooks/exhaustive-deps` | R-04, D-02, W-03 | Frontend y Tests +0,25 | 4 más 3 | Sí |
| 7 | Tope de cuerpo chunked y límite del endpoint de campañas | B-04, B-05 | Backend application +0,25 | 4 | Sí (seguridad) |
| 8 | Test de reglas de import en CI | R-21 (parte test) | Modularidad +0,25 | 1 | No (va con la fila 2) |
| 9 | mypy: baseline en CI y luego bajar los 163 errores | R-03, B-10 | Tests y Backend +0,25 | 2 (baseline) a 12 | Sí |
| 10 | Docstrings con el porqué en las 15 funciones mayores | R-16 | Documentación +0,25 | 3 | No |
| 11 | Decisión sobre el camino `voltage_limited` | B-06 | Dominio +0,25; coherencia de docs | 3 | Sí (decisión de producto) |
| 12 | Quitar el id de `n1_worst` y test de no-ranking | B-07 | Alineación con `cyber.md` | 2 | Sí (decisión de guardrail) |
| 13 | Tope diario de costo del asistente y `ASSISTANT_ENABLED` | B-17 | MCP/asistente +0,25 | 4 | Sí (decisión abierta de `plan.md` sección 9) |
| 14 | Aclarar en README y UI qué validan V1-V10 | B-03 | Honestidad de diseño | 1 | No (parte de la fila 3) |
| 15 | Fixtures de los 4 adaptadores y `CachedHttp`, `fail_under` | R-05 | Backend application +0,25 | 6,5 | Sí |
| 16 | Dividir `CascadeApp` y probar `useSession` | W-01, W-04 | Frontend +0,5 | 18 | Sí (dos issues) |
| 17 | Dividir `validate_snapshot`, `_cycle` y mover rutas en línea de `create_app` | B-09, R-20 | Modularidad +0,25 | 3 a 17 | Sí (bajo, post-evento) |
| 18 | Mover `mcp/{client,state,toolbox,tools,specs,digest}` a un paquete neutro | B-08, R-21 | Modularidad +0,25 | 6 a 8 | Sí |
| 19 | Endurecer descarga y proveniencia de scripts de datos, declarar `scipy` | D-01, D-03, R-23 | Datos +0,5 | 6,25 | Sí |
| 20 | Constantes de la UI desde el backend y tipos TS generados | W-05 | Frontend +0,25 | 8 más 8 | Sí |
| 21 | `ErrorBoundary`, borrar o `lazy` mapas 1 y 2, dividir bundle | W-08, W-07, R-24 | Frontend +0,25 | 5 a 7 | No (agrupar en uno) |
| 22 | ADRs, archivo de changelog, licencias de datos | R-18, R-17, D-07 | Documentación +0,1 | 4,5 | No |

Resumen de impacto: filas 1 a 4 (unas 12 a 13 h) llevan la estimación global de 3,5 a unos 3,9. Sumando 6, 7, 8 y 10 (unas 17 h más) se acerca a 4,2. Las filas 16 a 20 son refactores mayores que conviene diferir salvo que sobre tiempo.

---

## 9. Qué no se pudo medir y por qué

1. **Estado de `upstream/main`.** El worktree está 32 commits atrás. No cambié de rama ni ejecuté pruebas allá (auditoría de solo lectura). No sé si los dos tests de caché siguen fallando tras la regeneración `a128793`.
2. **Cobertura del frontend.** `@vitest/coverage-v8` no está instalado y no se instaló nada.
3. **Comportamiento de GitHub Actions.** Se leyó el YAML y `gh run list` (8 ejecuciones recientes); no se abrió el log de la corrida fallida de `lint` en la rama `feat/assistant-chat` ni se disparó ningún workflow.
4. **`docker compose up` desde cero** (issue #79 sección 6). Requiere Docker y construye dos imágenes; quedó fuera del presupuesto de solo lectura. Solo se leyeron `docs/docker.md` y `docker-compose.yml`.
5. **Pruebas de extremo a extremo y comportamiento en navegador.** No existe suite e2e; sin jsdom no se ejercitó ningún componente. `CascadeApp` se evaluó leyéndolo, no ejecutándolo.
6. **Servidor MCP y adaptador Bedrock.** Los paquetes `mcp` y `anthropic` no están en el entorno de pruebas por defecto, así que `mcp/server.py` no se ejecutó (0 % de cobertura, dos archivos de tests omitidos). No se llamó a ningún modelo.
7. **Secretos en rutas generadas y binarios.** El barrido del historial excluyó `web/public/cache`, `data/processed`, `docs/openapi` y archivos de lock; no lee blobs binarios. `gitleaks` omite los commits de merge (239 de 296 commits escaneados). `trufflehog` no está instalado. Las restricciones por URL del token Mapbox viven en la cuenta de Mapbox y no se ven desde el repo.
8. **`npm audit`.** Las 11 vulnerabilidades (3 moderadas, 8 altas) no se analizaron.
9. **Duplicación de código en la web.** `pylint` solo cubre Python; para `web/` se usaron los `grep` de constantes duplicadas (no se corrió `jscpd`).
10. **El hook de pre-commit con bash 4 o más.** Solo se verificó el fallo de `mapfile` con bash 3.2; no se ejecutó el hook completo.
11. **Rendimiento y carga.** Salvo la campaña de 120 corridas (26,9 s), no hubo pruebas de carga sobre la API ni medición de tiempos de render en la web.
12. **mypy en modo estricto** y reglas adicionales de ruff (`--select ALL`). Solo se midió la configuración existente.
13. **Infraestructura** (`*.tf`, `deploy.sh`, Dockerfiles, contenido de workflows más allá de qué comandos ejecutan): fuera de alcance por instrucción.
14. **Puntaje del evaluador del issue #79.** La rúbrica oficial y la posible revisión automática no son visibles; el puntaje global es una estimación propia.

### 9.1 Estado del worktree al terminar

`git status --porcelain` muestra ` D web/node_modules` (el symlink versionado que `npm ci` reemplazó por un directorio real; ver R-09). No es un archivo creado por la auditoría de forma voluntaria y no se restauró. Restauración, si se reutiliza el worktree: `git -C <worktree> checkout -- web/node_modules`. El único archivo nuevo no ignorado es `reports/technical-review.md`. `backend/.venv`, `backend/.pytest_cache`, `web/node_modules/` (directorio) y `web/dist/` están ignorados; `backend/.coverage` se movió a `/tmp/code-audit/raw/`.

### 9.2 Verificación de calibración

Para este informe abrí las líneas citadas en el worktree. Confirmadas (36): `engine.py:287-288`, `:417`; `limits.py:19,80,136-141`; `assistant.py:66-67`; `simulation_routes.py:221,267,284,305,372`; `run_campaign.py:35`; `execution.py:415-426`; `digital.py:157-160`; `params.py:45-49`; `rng.py:14-23`; `assistant_routes.py:29-32`; `build_regional.py:123,128`; `container.py:5-6`; `agent_openapi.py:141`; `unify.py:126`; `test_llm_commander.py:128-130`; `test_engine_cases.py:96,123`; `test_grid_simulation.py:80-84`; `health.py:168-198`; `test_health.py:55-59`; `test_mcp_tools.py:153-157`; `CascadeApp.tsx:36,50,130,180,476`; `sessionApi.ts:6,28-45,96`; `useSession.ts:6,68-73`; `main.tsx:9-18`; `mapboxMap.ts:53`; `baseMap.ts:79`; `NetworkPanel.tsx:9`; `build_operating_points.py:143-155`; `build_node_index.py:180-185`; `build_baseline_opf.py:20-30`; `lint.yml:1-40`; `deploy.yml:1-25`; `lint.sh:9,31-32,63`; `docs/stack.md:3,7,9`; `docs/plan.md:8,16,97,107,149,151`; `docs/mapa3.md:251,263,269`; `docs/datasets.md:102,141,186`; `session_routes.py:222,366`; `sessions.py:207,211`; `.gitignore:18`.

Corregidas respecto de los insumos: el `mapfile` está en `scripts/hooks/pre-commit:16` (los insumos decían `:12`); el `RUN npm run build` de la imagen web está en `infrastructure/docker/web.Dockerfile:12` (decían `:11`); se descartó la frase de que `docs/datasets.md:141` dice "This step has not been done" (esa línea dice "The engine has about 10-14 nodes"); `test_llm_commander.py` se cita como `:128-130`; se unificó en "unas 11" las funciones de corridas de `sessionApi.ts` que la UI no llama (un insumo decía 9 y listaba 11 nombres); `docs/stack.md:3` sí dice "Not implemented: the cascade engine ...", pero también enumera lo implementado, así que la obsolescencia es parcial.

Contradicciones entre insumos resueltas: puntaje de scripts de datos 3,5 contra mi 3 (se baja a 3 por R-23, verificado: 0 apariciones de `scipy` en `backend/uv.lock` y ausencia en `pyproject.toml`); el recuento de commits de diferencia con `upstream/main` pasó de 17 a 32 porque las referencias locales avanzaron durante la auditoría.

---

## 10. Apéndice: salidas crudas

Archivos completos en `/tmp/code-audit/raw/`: `ruff-check.txt`, `ruff-format.txt`, `mypy.txt` (251 líneas), `pytest-cov.txt` (193 líneas), `npm-ci.txt`, `tsc.txt`, `vitest.txt`, `build.txt`, además de `radon-*.txt`, `metrics-ast.txt`, `cachediff.txt`, `pytest-skips.txt`, `cov-pkg.txt`, `gitleaks*.json`, `pylint-dup*.txt`.

### 10.1 ruff check (`raw/ruff-check.txt`)

```text
Using CPython 3.12.13
Creating virtual environment at: .venv
   Building cascadasen @ file:///Users/alonsoutreras/Desktop/Hackathon/platanus-hack-26-cl-team-9/.worktrees/code-audit/backend
      Built cascadasen @ file:///Users/alonsoutreras/Desktop/Hackathon/platanus-hack-26-cl-team-9/.worktrees/code-audit/backend
Installed 49 packages in 129ms
All checks passed!
EXIT:0
```

### 10.2 ruff format (`raw/ruff-format.txt`)

```text
162 files already formatted
EXIT:0
```

### 10.3 mypy (`raw/mypy.txt`, 251 líneas)

Totales: 179 errores en 33 de 118 archivos (tabla por código en la sección 4.3). Primeras 60 líneas y última línea:

```text
src/cascadasen/domain/simulation/params.py:15: error: Library stubs not installed for "yaml"  [import-untyped]
src/cascadasen/domain/simulation/params.py:15: note: Hint: "python3 -m pip install types-PyYAML"
src/cascadasen/application/grid_queries.py:11: error: Library stubs not installed for "networkx"  [import-untyped]
src/cascadasen/application/grid_queries.py:11: note: Hint: "python3 -m pip install types-networkx"
src/cascadasen/application/grid_queries.py:11: note: (or run "mypy --install-types" to install all missing stub packages)
src/cascadasen/application/grid_queries.py:11: note: See https://mypy.readthedocs.io/en/stable/running_mypy.html#missing-imports
src/cascadasen/application/grid_queries.py:216: error: Need type annotation for "tech"  [var-annotated]
src/cascadasen/application/grid_queries.py:469: error: Generator has incompatible item type "object"; expected "bool"  [misc]
src/cascadasen/application/grid_queries.py:469: error: Unsupported operand types for >= ("int" and "object")  [operator]
src/cascadasen/application/grid_queries.py:500: error: Argument 1 to "_point" has incompatible type "float | None"; expected "float"  [arg-type]
src/cascadasen/application/grid_queries.py:500: error: Argument 2 to "_point" has incompatible type "float | None"; expected "float"  [arg-type]
src/cascadasen/application/grid_queries.py:531: error: Argument 2 to "_point" has incompatible type "float | None"; expected "float"  [arg-type]
src/cascadasen/domain/validation.py:12: error: Library stubs not installed for "networkx"  [import-untyped]
src/cascadasen/domain/validation.py:116: error: Unsupported operand types for <= ("float" and "None")  [operator]
src/cascadasen/domain/validation.py:116: note: Right operand is of type "float | None"
src/cascadasen/domain/validation.py:116: error: Unsupported operand types for >= ("float" and "None")  [operator]
src/cascadasen/domain/validation.py:116: note: Left operand is of type "float | None"
src/cascadasen/domain/validation.py:148: error: Value of type variable "SupportsRichComparisonT" of "max" cannot be "float | None"  [type-var]
src/cascadasen/domain/validation.py:148: error: Unsupported operand types for < ("int" and "None")  [operator]
src/cascadasen/domain/validation.py:148: note: Left operand is of type "float | None"
src/cascadasen/domain/validation.py:148: error: Value of type variable "SupportsRichComparisonT" of "min" cannot be "float | None"  [type-var]
src/cascadasen/domain/validation.py:148: error: Unsupported operand types for > ("int" and "None")  [operator]
src/cascadasen/domain/validation.py:149: error: Value of type variable "SupportsRichComparisonT" of "max" cannot be "float | None"  [type-var]
src/cascadasen/domain/validation.py:149: error: Value of type variable "SupportsRichComparisonT" of "min" cannot be "float | None"  [type-var]
src/cascadasen/domain/validation.py:163: error: Argument 1 to "comuna_of_point" has incompatible type "float | None"; expected "float"  [arg-type]
src/cascadasen/domain/validation.py:163: error: Argument 2 to "comuna_of_point" has incompatible type "float | None"; expected "float"  [arg-type]
src/cascadasen/domain/validation.py:202: error: Argument "key" to "max" has incompatible type "Callable[[Node], float | None]"; expected "Callable[[Node], SupportsDunderLT[Any] | SupportsDunderGT[Any]]"  [arg-type]
src/cascadasen/domain/validation.py:202: error: Incompatible return value type (got "float | None", expected "SupportsDunderLT[Any] | SupportsDunderGT[Any]")  [return-value]
src/cascadasen/domain/validation.py:205: error: Argument "key" to "min" has incompatible type "Callable[[Node], float | None]"; expected "Callable[[Node], SupportsDunderLT[Any] | SupportsDunderGT[Any]]"  [arg-type]
src/cascadasen/domain/validation.py:205: error: Incompatible return value type (got "float | None", expected "SupportsDunderLT[Any] | SupportsDunderGT[Any]")  [return-value]
src/cascadasen/domain/validation.py:297: error: Incompatible types in assignment (expression has type "Node", variable has type "str")  [assignment]
src/cascadasen/domain/validation.py:298: error: "str" has no attribute "kind"  [attr-defined]
src/cascadasen/domain/validation.py:300: error: "str" has no attribute "name"  [attr-defined]
src/cascadasen/domain/topology_inference.py:159: error: Incompatible types in assignment (expression has type "tuple[int, int]", variable has type "int")  [assignment]
src/cascadasen/domain/topology_inference.py:160: error: Invalid index type "int" for "dict[tuple[int, int], dict[Any, Any]]"; expected type "tuple[int, int]"  [index]
src/cascadasen/domain/cascade/engine.py:181: error: Incompatible return value type (got "tuple[int | None, int | None] | None", expected "tuple[int, int] | None")  [return-value]
src/cascadasen/infrastructure/sources/pypsa_cl.py:9: error: Library stubs not installed for "openpyxl"  [import-untyped]
src/cascadasen/infrastructure/sources/pypsa_cl.py:9: note: Hint: "python3 -m pip install types-openpyxl"
src/cascadasen/domain/simulation/network.py:17: error: Library stubs not installed for "networkx"  [import-untyped]
src/cascadasen/domain/simulation/network.py:234: error: Incompatible types in assignment (expression has type "float", target has type "int")  [assignment]
src/cascadasen/domain/simulation/network.py:299: error: Need type annotation for "lines"  [var-annotated]
src/cascadasen/domain/simulation/network.py:325: error: Incompatible types in assignment (expression has type "float", target has type "int")  [assignment]
src/cascadasen/domain/simulation/network.py:339: error: Generator has incompatible item type "float | None"; expected "bool"  [misc]
src/cascadasen/domain/simulation/network.py:340: error: Generator has incompatible item type "float | None"; expected "bool"  [misc]
src/cascadasen/domain/simulation/network.py:360: error: Argument 1 to "haversine_km" has incompatible type "float | None"; expected "float"  [arg-type]
src/cascadasen/domain/simulation/network.py:360: error: Argument 2 to "haversine_km" has incompatible type "float | None"; expected "float"  [arg-type]
src/cascadasen/domain/simulation/network.py:360: error: Argument 3 to "haversine_km" has incompatible type "float | None"; expected "float"  [arg-type]
src/cascadasen/domain/simulation/network.py:360: error: Argument 4 to "haversine_km" has incompatible type "float | None"; expected "float"  [arg-type]
src/cascadasen/domain/unify.py:25: error: Library stubs not installed for "networkx"  [import-untyped]
src/cascadasen/domain/unify.py:166: error: Dict entry 0 has incompatible type "str": "int | None"; expected "str": "str"  [dict-item]
src/cascadasen/domain/unify.py:166: error: Dict entry 1 has incompatible type "str": "str | None"; expected "str": "str"  [dict-item]
src/cascadasen/domain/unify.py:332: error: Argument 1 to "_resolve_end" of "GridUnifier" has incompatible type "str | None"; expected "str"  [arg-type]
src/cascadasen/domain/unify.py:333: error: Argument 1 to "_resolve_end" of "GridUnifier" has incompatible type "str | None"; expected "str"  [arg-type]
src/cascadasen/domain/unify.py:396: error: Argument 1 to "via_non_substations" has incompatible type "str | None"; expected "str"  [arg-type]
src/cascadasen/domain/unify.py:396: error: Argument 2 to "via_non_substations" has incompatible type "str | None"; expected "str"  [arg-type]
src/cascadasen/domain/unify.py:417: error: Argument "source_node" to "Edge" has incompatible type "str | None"; expected "str"  [arg-type]
src/cascadasen/domain/unify.py:418: error: Argument "target_node" to "Edge" has incompatible type "str | None"; expected "str"  [arg-type]
src/cascadasen/domain/unify.py:618: error: List comprehension has incompatible type List[float | None]; expected List[float]  [misc]
src/cascadasen/domain/unify.py:622: error: List comprehension has incompatible type List[float | None]; expected List[float]  [misc]
src/cascadasen/domain/unify.py:654: error: Argument 1 to "mean" has incompatible type "list[float | None]"; expected "_SupportsArray[dtype[integer[Any] | numpy.bool[builtins.bool] | object_]] | _NestedSequence[_SupportsArray[dtype[integer[Any] | numpy.bool[builtins.bool] | object_]]] | float | _NestedSequence[float]"  [arg-type]
[...]
Found 179 errors in 33 files (checked 118 source files)
EXIT:1
```

### 10.4 pytest con cobertura (`raw/pytest-cov.txt`)

Fallos, advertencia y tabla de cobertura completa, tal como salió (incluye la columna `Missing`):

```text
=================================== FAILURES ===================================
_ test_the_committed_cache_matches_the_engine_for_a_single_cut[feb2025-1500-R239] _

sim = <cascadasen.application.grid_simulation.GridSimulator object at 0x114c68b30>
point = 'feb2025-1500', line = 'R239'

    @pytest.mark.parametrize("point, line", [("feb2025-1500", "R239"), ("nov2026-2000", "R001")])
    def test_the_committed_cache_matches_the_engine_for_a_single_cut(sim, point, line):
        """The web reads the cache for one cut and this service for several: they must agree (regenerate with cascadasen-cache)."""
        import json
    
        cached = json.loads((REPO_ROOT / f"web/public/cache/{point}/{line}.json").read_text())
>       assert sim.simulate_workflow(point, [line], [])["timeline"] == cached
E       AssertionError: assert {'scenario': ...': False, ...} == {'scenario': ...': False, ...}
E         
E         Omitting 9 identical items, use -vv to show
E         Differing items:
E         {'frames': [{'t': 0.0, 'edges': {'R000': {'flow_mw': -12, 'status': 'ok', 'loading': np.float64(0.139)}, 'R001': {'flo...004', 'B005', ...], 'islands': [{'buses': 115, 'gen_mw': 0, 'load_mw': 0}, {'buses': 73, 'gen_mw': 0, 'load_mw': 0}]}]} != {'frames': [{'t': 0.0, 'edges': {'R000': {'flow_mw': -12, 'status': 'ok', 'loading': 0.139}, 'R001': {'flow_mw': -15, ...004', 'B005', ...], 'islands': [{'buses': 115, 'gen_mw': 0, 'load_mw': 0}, {'buses': 73, 'gen_mw': 0, 'load_mw': 0}]}]}
E         Use -v to get more diff

tests/unit/test_grid_simulation.py:84: AssertionError
_ test_the_committed_cache_matches_the_engine_for_a_single_cut[nov2026-2000-R001] _

sim = <cascadasen.application.grid_simulation.GridSimulator object at 0x114c68b30>
point = 'nov2026-2000', line = 'R001'

    @pytest.mark.parametrize("point, line", [("feb2025-1500", "R239"), ("nov2026-2000", "R001")])
    def test_the_committed_cache_matches_the_engine_for_a_single_cut(sim, point, line):
        """The web reads the cache for one cut and this service for several: they must agree (regenerate with cascadasen-cache)."""
        import json
    
        cached = json.loads((REPO_ROOT / f"web/public/cache/{point}/{line}.json").read_text())
>       assert sim.simulate_workflow(point, [line], [])["timeline"] == cached
E       AssertionError: assert {'scenario': ...': False, ...} == {'scenario': ...': False, ...}
E         
E         Omitting 9 identical items, use -vv to show
E         Differing items:
E         {'frames': [{'t': 0.0, 'edges': {'R000': {'flow_mw': 8, 'status': 'ok', 'loading': np.float64(0.088)}, 'R001': {'flow_...ok', 'loading': np.float64(0.274)}, ...}, 'dark': [], 'islands': [{'buses': 188, 'gen_mw': 10934, 'load_mw': 10934}]}]} != {'frames': [{'t': 0.0, 'edges': {'R000': {'flow_mw': 8, 'status': 'ok', 'loading': 0.088}, 'R001': {'flow_mw': 0, 'sta... 'status': 'ok', 'loading': 0.274}, ...}, 'dark': [], 'islands': [{'buses': 188, 'gen_mw': 10934, 'load_mw': 10934}]}]}
E         Use -v to get more diff

tests/unit/test_grid_simulation.py:84: AssertionError
__________________ test_bedrock_adapters_use_the_aws_profile ___________________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x11c8cbd70>

    def test_bedrock_adapters_use_the_aws_profile(monkeypatch):
>       import anthropic
E       ModuleNotFoundError: No module named 'anthropic'

tests/unit/test_llm_commander.py:130: ModuleNotFoundError
=============================== warnings summary ===============================
.venv/lib/python3.12/site-packages/fastapi/testclient.py:1
  /Users/alonsoutreras/Desktop/Hackathon/platanus-hack-26-cl-team-9/.worktrees/code-audit/backend/.venv/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
================================ tests coverage ================================
______________ coverage: platform darwin, python 3.12.13-final-0 _______________

Name                                                                  Stmts   Miss  Cover   Missing
---------------------------------------------------------------------------------------------------
src/cascadasen/__init__.py                                                0      0   100%
src/cascadasen/api/__init__.py                                            0      0   100%
src/cascadasen/api/agent_openapi.py                                      58      7    88%   137, 141-146, 150
src/cascadasen/api/app.py                                               149     16    89%   103, 154, 202, 227, 240-241, 245-246, 254, 258, 270, 283, 291, 304, 309-311
src/cascadasen/api/assistant_routes.py                                  119     11    91%   89, 104-106, 206-207, 210-212, 259-260
src/cascadasen/api/grid_routes.py                                        56      2    96%   77-78
src/cascadasen/api/limits.py                                             91      3    97%   35, 59, 67
src/cascadasen/api/schemas.py                                            82      0   100%
src/cascadasen/api/session_routes.py                                    257     15    94%   93-105, 167, 169, 177-178, 577-578, 583-584, 608, 786, 788
src/cascadasen/api/session_schemas.py                                   117      0   100%
src/cascadasen/api/simulation_routes.py                                 118     10    92%   50-62, 161-162, 178, 314, 316
src/cascadasen/api/simulation_schemas.py                                202      0   100%
src/cascadasen/application/__init__.py                                    0      0   100%
src/cascadasen/application/assistant.py                                 131      0   100%
src/cascadasen/application/build_grid.py                                 35     18    49%   26-45
src/cascadasen/application/build_regional.py                            125     73    42%   37, 60-61, 64-67, 69-70, 93-95, 98-119, 123-172, 176-192, 196
src/cascadasen/application/cache_builder.py                              49     33    33%   25-29, 33-34, 42-66, 101, 105-115, 119
src/cascadasen/application/grid_health.py                                40     20    50%   33-42, 46-61, 65
src/cascadasen/application/grid_queries.py                              273     51    81%   121-123, 170, 172, 174, 176, 178, 180, 182, 184, 218-219, 256, 258, 260, 272-275, 288-298, 301-306, 311-335, 338, 345-347, 353, 374-377, 413-414, 442, 481, 484, 493, 495, 499, 504, 527-528, 539, 557
src/cascadasen/application/grid_simulation.py                            55      2    96%   70-71
src/cascadasen/application/grids.py                                     183     50    73%   146, 159, 283, 302-307, 314-362, 366
src/cascadasen/application/run_campaign.py                              182      7    96%   94, 146, 154, 157, 161, 197, 249
src/cascadasen/application/run_experiment.py                            193      3    98%   137, 207, 268
src/cascadasen/application/sessions.py                                  292     10    97%   72, 142, 364, 386, 427, 439, 456, 497-498, 501
src/cascadasen/application/simulate.py                                  129     26    80%   61-68, 75-81, 98, 104, 110, 115-120, 178, 204
src/cascadasen/application/simulation_service.py                         49      1    98%   55
src/cascadasen/application/theater_world.py                              62      2    97%   32, 79
src/cascadasen/cli.py                                                    23     23     0%   3-35
src/cascadasen/domain/__init__.py                                         0      0   100%
src/cascadasen/domain/agents/__init__.py                                  0      0   100%
src/cascadasen/domain/agents/adversary.py                               110      1    99%   122
src/cascadasen/domain/agents/auditor.py                                  56      2    96%   75-76
src/cascadasen/domain/agents/base.py                                     36      0   100%
src/cascadasen/domain/agents/commander.py                               110      2    98%   61, 138
src/cascadasen/domain/agents/isr.py                                     101      1    99%   76
src/cascadasen/domain/agents/logistics.py                                53      2    96%   49, 77
src/cascadasen/domain/agents/operations.py                               46      1    98%   27
src/cascadasen/domain/agents/stabilization.py                           117      3    97%   49, 112, 148
src/cascadasen/domain/cascade/__init__.py                                 0      0   100%
src/cascadasen/domain/cascade/engine.py                                 208      1    99%   231
src/cascadasen/domain/cascade/flow.py                                    44      0   100%
src/cascadasen/domain/cascade/frequency.py                              123      0   100%
src/cascadasen/domain/cascade/health.py                                 103      2    98%   71, 144
src/cascadasen/domain/cascade/network.py                                 60      0   100%
src/cascadasen/domain/cascade/overlay.py                                365     31    92%   156, 161, 235, 248, 261, 273, 282, 286, 328, 340, 349-350, 356, 410, 419-421, 444-445, 461-462, 477, 495, 501, 523, 530, 537, 550, 555, 585, 591
src/cascadasen/domain/cascade/scenario.py                                67      1    99%   27
src/cascadasen/domain/geo.py                                             85      6    93%   36-39, 44, 56
src/cascadasen/domain/grids.py                                           54      1    98%   153
src/cascadasen/domain/model.py                                          330      0   100%
src/cascadasen/domain/naming.py                                          53      3    94%   53, 59, 65
src/cascadasen/domain/ports.py                                           39      0   100%
src/cascadasen/domain/regional.py                                       146      1    99%   233
src/cascadasen/domain/regional_network.py                               383     15    96%   226-227, 308, 322, 325-326, 449-451, 477, 506, 549, 601, 613, 616
src/cascadasen/domain/regional_reduction.py                             257      9    96%   113, 122, 159, 161, 223, 277, 314-315, 335
src/cascadasen/domain/simulation/__init__.py                              0      0   100%
src/cascadasen/domain/simulation/consequence.py                          18      2    89%   26, 28
src/cascadasen/domain/simulation/defenses.py                             45      1    98%   41
src/cascadasen/domain/simulation/engine.py                              297     42    86%   106, 133, 144-145, 151-154, 160-187, 191-192, 197-200, 207, 218-220, 275
src/cascadasen/domain/simulation/frequency.py                           150      6    96%   37, 95-99
src/cascadasen/domain/simulation/grid.py                                166      9    95%   129-130, 134, 148-150, 166, 246, 275
src/cascadasen/domain/simulation/network.py                             271      7    97%   186, 201, 216, 290, 308, 331, 353
src/cascadasen/domain/simulation/params.py                               67      6    91%   67-68, 70, 78, 102-103
src/cascadasen/domain/simulation/powerflow.py                            52      0   100%
src/cascadasen/domain/simulation/timeline.py                             67      5    93%   31-32, 41, 105, 107
src/cascadasen/domain/theater/__init__.py                                 0      0   100%
src/cascadasen/domain/theater/areas.py                                  134      3    98%   61, 159, 188
src/cascadasen/domain/theater/audit.py                                   38      1    97%   61
src/cascadasen/domain/theater/catalog.py                                 34      0   100%
src/cascadasen/domain/theater/config.py                                  71      1    99%   79
src/cascadasen/domain/theater/crews.py                                   83      1    99%   57
src/cascadasen/domain/theater/cycle.py                                  421     15    96%   151, 264, 266, 268, 273, 333-336, 432, 451, 462-470, 478, 813
src/cascadasen/domain/theater/decisions.py                               76      2    97%   27, 86
src/cascadasen/domain/theater/digital.py                                157      4    97%   32, 151, 159, 175
src/cascadasen/domain/theater/evaluator.py                              120      2    98%   62, 176
src/cascadasen/domain/theater/execution.py                              363     16    96%   79, 141, 151-153, 230-232, 241, 252, 268-269, 312, 339, 532, 534
src/cascadasen/domain/theater/grid.py                                   320     24    92%   103, 138, 141-142, 155-157, 165-169, 190-194, 231, 325-326, 357, 403, 412, 433
src/cascadasen/domain/theater/narrative.py                               49      2    96%   31, 46
src/cascadasen/domain/theater/resources.py                               42      2    95%   41, 57
src/cascadasen/domain/theater/rng.py                                      9      0   100%
src/cascadasen/domain/theater/state.py                                   98      0   100%
src/cascadasen/domain/theater/stochastic.py                              55      1    98%   47
src/cascadasen/domain/theater/validator.py                              132      9    93%   75, 113, 141-146, 161
src/cascadasen/domain/theater/world.py                                   15      0   100%
src/cascadasen/domain/topology_inference.py                             177     78    56%   64, 68, 86-92, 101-106, 112-129, 138-149, 157-162, 165-170, 173-183, 238-253, 257
src/cascadasen/domain/unify.py                                          538    112    79%   113-114, 154-155, 192-194, 236-250, 259-262, 284-289, 299-300, 312-323, 339-372, 375-376, 379-380, 398-402, 409-410, 458-470, 474-476, 489, 497-502, 608-612, 625, 632, 635, 678-679, 695-696, 698, 737-743, 761-763, 804, 807, 809, 811, 822, 842-844, 897, 927, 956
src/cascadasen/domain/validation.py                                     158      6    96%   66, 161, 218-219, 336, 376
src/cascadasen/infrastructure/__init__.py                                 0      0   100%
src/cascadasen/infrastructure/arcgis.py                                  31     26    16%   21-59
src/cascadasen/infrastructure/container.py                               55     20    64%   31-38, 50, 52-54, 61-64, 79-91, 96-97
src/cascadasen/infrastructure/document_store.py                         135      8    94%   134-136, 154, 175-177, 187, 190
src/cascadasen/infrastructure/exporters.py                               35     23    34%   23, 26-52, 55-71
src/cascadasen/infrastructure/grid_store.py                              59      7    88%   17, 36, 50-52, 57, 68, 87
src/cascadasen/infrastructure/http.py                                    53     34    36%   28-32, 35-44, 49-61, 64-66, 70, 73-74
src/cascadasen/infrastructure/inprocess.py                               16      0   100%
src/cascadasen/infrastructure/llm.py                                     97     21    78%   85-104, 147, 161, 210-219
src/cascadasen/infrastructure/llm_tools.py                               59      6    90%   106-111
src/cascadasen/infrastructure/settings.py                                76      3    96%   97, 105, 117
src/cascadasen/infrastructure/snapshot_repository.py                     62     17    73%   31-41, 45-47, 100-104
src/cascadasen/infrastructure/sources/__init__.py                         0      0   100%
src/cascadasen/infrastructure/sources/ide_energia.py                     61     44    28%   25-28, 32, 39-40, 43, 46-138, 156-158
src/cascadasen/infrastructure/sources/ine_censo.py                       54     38    30%   22-41, 52-54, 57-128
src/cascadasen/infrastructure/sources/infotecnica.py                     37     26    30%   13-15, 22-23, 26, 29-93
src/cascadasen/infrastructure/sources/pypsa_cl.py                        62     44    29%   20-23, 27-30, 34-35, 42-44, 47-57, 60-129
src/cascadasen/infrastructure/sources/regional/__init__.py                0      0   100%
src/cascadasen/infrastructure/sources/regional/energia_argentina.py      93     10    89%   57-58, 76-80, 89, 95, 176
src/cascadasen/infrastructure/sources/regional/epe_brasil.py             54      5    91%   46-47, 52, 103, 120
src/cascadasen/infrastructure/sources/regional/ons_brasil.py             59      4    93%   31-32, 40, 81
src/cascadasen/infrastructure/sources/regional/osinergmin_peru.py        58      6    90%   37-38, 81, 88, 106, 123
src/cascadasen/infrastructure/sources/regional/osm_overpass.py           56      5    91%   27, 33, 96, 113, 130
src/cascadasen/mcp/__init__.py                                            0      0   100%
src/cascadasen/mcp/client.py                                             66     21    68%   29, 33, 35-37, 41-44, 74-75, 77-81, 84, 91-92, 103, 106
src/cascadasen/mcp/digest.py                                             86     38    56%   20, 79-95, 113-151, 168-176, 236-240
src/cascadasen/mcp/server.py                                             17     17     0%   7-32
src/cascadasen/mcp/specs.py                                              30      0   100%
src/cascadasen/mcp/state.py                                              15      2    87%   21, 26
src/cascadasen/mcp/toolbox.py                                            66      7    89%   31-32, 40-41, 86-88
src/cascadasen/mcp/tools.py                                             127     56    56%   80-86, 107-111, 120-123, 128-129, 157-158, 181-187, 194-199, 203-205, 212-214, 219-221, 225-227, 261-262, 266, 287, 289, 307, 334-335, 343-345, 355, 360-361, 366-369
src/cascadasen/sim_fixtures.py                                           57     19    67%   86-87, 93-108, 112
---------------------------------------------------------------------------------------------------
TOTAL                                                                 11915   1329    89%
=========================== short test summary info ============================
FAILED tests/unit/test_grid_simulation.py::test_the_committed_cache_matches_the_engine_for_a_single_cut[feb2025-1500-R239]
FAILED tests/unit/test_grid_simulation.py::test_the_committed_cache_matches_the_engine_for_a_single_cut[nov2026-2000-R001]
FAILED tests/unit/test_llm_commander.py::test_bedrock_adapters_use_the_aws_profile
3 failed, 380 passed, 4 skipped, 1 warning in 27.36s
EXIT:1
```

### 10.5 tsc (`raw/tsc.txt`) y npm ci (`raw/npm-ci.txt`)

```text
EXIT_CODE=0
--- npm ci ---
npm warn reify Removing non-directory /Users/alonsoutreras/Desktop/Hackathon/platanus-hack-26-cl-team-9/.worktrees/code-audit/web/node_modules

added 178 packages, and audited 179 packages in 4s

26 packages are looking for funding
  run `npm fund` for details

11 vulnerabilities (3 moderate, 8 high)

To address issues that do not require attention, run:
  npm audit fix

To address all issues (including breaking changes), run:
  npm audit fix --force

Run `npm audit` for details.
npm ci  1.89s user 3.08s system 112% cpu 4.421 total
EXIT_CODE=0
```

### 10.6 vitest (`raw/vitest.txt`)

```text

 RUN  v5.1.1 /Users/alonsoutreras/Desktop/Hackathon/platanus-hack-26-cl-team-9/.worktrees/code-audit/web


 Test Files  13 passed (13)
      Tests  74 passed (74)
   Start at  23:12:10
   Duration  661ms (import 63%, transform 28%, tests 6%, worker 2%)

EXIT_CODE=0
```

### 10.7 build (`raw/build.txt`)

```text

> cascadasen-web@0.0.0 build
> tsc --noEmit && vite build

vite v8.3.8 building client environment for production...
transforming...
✓ 1807 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                                                           0.72 kB │ gzip:   0.37 kB
dist/assets/roboto-greek-ext-wght-normal-Bgw4czJT.woff2                   4.34 kB
dist/assets/plants-BYb-4L9S.geojson                                       4.37 kB
dist/assets/roboto-condensed-greek-ext-wght-normal-CuKbLwpm.woff2         4.62 kB
dist/assets/roboto-mono-vietnamese-wght-normal-DlC-zuDL.woff2            10.30 kB
dist/assets/manifest-CecPKAxw.json                                       11.94 kB │ gzip:   3.53 kB
dist/assets/roboto-mono-greek-wght-normal-BJJTbwTT.woff2                 14.04 kB
dist/assets/roboto-vietnamese-wght-normal-_f1XEJpo.woff2                 14.34 kB
dist/assets/roboto-condensed-vietnamese-wght-normal-BQ3qeiTz.woff2       16.15 kB
dist/assets/substations-CJl9538j.geojson                                 16.56 kB
dist/assets/roboto-greek-wght-normal-DlT9XTxE.woff2                      17.62 kB
dist/assets/roboto-mono-cyrillic-wght-normal-HUlVHixE.woff2              18.59 kB
dist/assets/lines-Bdp7Jlgl.geojson                                       19.44 kB
dist/assets/roboto-symbols-wght-normal-B7iHSfaG.woff2                    20.55 kB
dist/assets/roboto-condensed-greek-wght-normal-Cvhr4n9Q.woff2            21.94 kB
dist/assets/roboto-mono-latin-ext-wght-normal-QAYlOegK.woff2             22.91 kB
dist/assets/roboto-cyrillic-wght-normal-fOt7epNf.woff2                   23.66 kB
dist/assets/plants-BVaA0G4U.geojson                                      24.39 kB
dist/assets/roboto-condensed-cyrillic-wght-normal-DcSt-2BC.woff2         28.86 kB
dist/assets/roboto-latin-ext-wght-normal-DYIxWhlt.woff2                  29.39 kB
dist/assets/plants-BK3LIrI6.geojson                                      30.22 kB
dist/assets/roboto-mono-latin-wght-normal-CZtBPCCa.woff2                 32.79 kB
dist/assets/roboto-condensed-latin-ext-wght-normal-Db2M7toj.woff2        33.96 kB
dist/assets/roboto-mono-cyrillic-ext-wght-normal-BUDPrIko.woff2          35.91 kB
dist/assets/roboto-cyrillic-ext-wght-normal-BCp_3N7R.woff2               36.65 kB
dist/assets/roboto-math-wght-normal-4a3xuzGk.woff2                       41.34 kB
dist/assets/roboto-latin-wght-normal-ccAYIvAh.woff2                      43.13 kB
dist/assets/roboto-condensed-cyrillic-ext-wght-normal-DhztH7TG.woff2     45.80 kB
dist/assets/roboto-condensed-latin-wght-normal-Cxzi1x1i.woff2            51.41 kB
dist/assets/substations-C3x4_-Fk.geojson                                 59.02 kB
dist/assets/chile-BrYacsNP.geojson                                       60.04 kB
dist/assets/outlines-CVyaUrEt.geojson                                    80.03 kB
dist/assets/lines-BHiSIN9L.geojson                                       82.73 kB
dist/assets/substations-hnJ2JFRV.geojson                                 91.66 kB
dist/assets/lines-Zkh-MYng.geojson                                      133.21 kB
dist/assets/plants-CUJAydQy.geojson                                     157.12 kB
dist/assets/substations-DA2jyh3G.geojson                                251.74 kB
dist/assets/lines-CL-iTlnQ.geojson                                      429.72 kB
dist/assets/plants-DfDVYR5x.geojson                                     637.61 kB
dist/assets/substations-CRKzQQRR.geojson                                715.19 kB
dist/assets/network-A42e_OEv.json                                       729.46 kB │ gzip: 102.55 kB
dist/assets/node_index-CwW7OtPc.json                                  1,418.30 kB │ gzip: 201.22 kB
dist/assets/lines-BAhwkoBw.geojson                                    1,488.32 kB
dist/assets/index-07W-0nJy.css                                           82.06 kB │ gzip:  13.52 kB
dist/assets/webgl-B2E6kPYH.js                                            18.84 kB │ gzip:   6.61 kB
dist/assets/get-attribute-from-layouts-Dd2gixpo.js                       19.20 kB │ gzip:   5.54 kB
dist/assets/array-utils-flat-BL8Cekj1.js                                 29.53 kB │ gzip:   9.53 kB
dist/assets/expression-C4x9yiMU.js                                       96.42 kB │ gzip:  29.17 kB
dist/assets/index-BAWzTLaT.js                                         2,991.39 kB │ gzip: 841.80 kB

[plugin builtin:vite-reporter] 
(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rolldownOptions.output.codeSplitting to improve chunking: https://rolldown.rs/reference/OutputOptions.codeSplitting
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
✓ built in 1.04s
EXIT_CODE=0
```

### 10.8 Diferencias de la caché (`raw/cachediff.txt`)

```text
feb2025-1500 R239 2
/frames[0]/edges/R183/status: engine='ok' cache='overload'
/frames[1]/edges/R183/status: engine='ok' cache='overload'
nov2026-2000 R001 5
/frames[0]/edges/R113/flow_mw: engine=-40 cache=-39
/frames[0]/edges/R113/status: engine='overload' cache='ok'
/frames[0]/edges/R206/status: engine='overload' cache='ok'
/frames[0]/edges/R122/status: engine='ok' cache='overload'
/frames[0]/edges/R065/status: engine='ok' cache='overload'
```
