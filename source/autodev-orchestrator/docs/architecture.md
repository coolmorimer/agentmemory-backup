# Architecture

AutoDev is a modular monolith with an independently runnable worker loop. FastAPI owns the control
plane; PostgreSQL is the durable source for projects, goals, DAG tasks, attempts, evidence, provider
state, approvals, deployments, incidents, and audit events. Redis is optional and replaceable: it
may fan out live events, but never decides task state.

The execution path is `goal → typed plan → DAG → SKIP LOCKED claim → persistent role/model route →
optional bounded provider advice → Codex coding agent → checks → independent review → scoped Git
commit → completion`. `WorkerPool` releases satisfied DAG
dependencies, claims up to its concurrency limit, renews leases, and requeues bounded failures.
`ExecutionEngine` assembles redacted repository and memory context and records deterministic evidence.

Adapters isolate Codex App Server, OpenAI-compatible providers, Ollama, AgentMemory, Git, browser QA,
Docker Compose, GitHub Actions, and webhooks. Project and task FSMs reject every undeclared transition.
The React control room and native VS Code activity-bar extension read the same APIs. The web UI also
receives replaceable live WebSocket events. Provider credentials are Fernet-encrypted before they
enter PostgreSQL and never cross a read API boundary.

Safety boundaries are enforced before side effects: privacy/budget routing, allowlisted command
families, secret scanning, staged-change protection, checks/review before commit, and approval plus
rollback prerequisites before production deployment.
