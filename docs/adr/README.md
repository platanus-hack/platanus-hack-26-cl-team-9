# Architecture decision records
Short records of decisions that shape the code and are expensive to reverse. Each one states the context, the decision, what follows from it and where the facts come from. Facts come from the docs they cite. When a doc and the code disagree, the code wins and the record needs an update.

Format of every record: `Status`, `Context`, `Decision`, `Consequences`, `Sources`. Number records in order and never renumber. A decision that is replaced keeps its file, with `Status: superseded by NNNN`.

| # | Decision | Status |
|---|---|---|
| [0001](0001-two-engines.md) | Two simulation engines: 13 areas and 188 buses | Accepted |
| [0002](0002-reduced-188-bus-network.md) | The cascade runs on a 188-bus reduction of PyPSA-CL | Accepted |
| [0003](0003-dc-power-flow.md) | DC power flow, with voltage collapse as a rule | Accepted |
| [0004](0004-sessions-on-s3-by-url-capability.md) | Sessions are JSON documents on S3, the session id is the capability | Accepted |
| [0005](0005-hexagonal-layering.md) | Hexagonal layering, enforced by a test | Accepted |
