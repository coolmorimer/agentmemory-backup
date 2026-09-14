# AutoDev Orchestrator implementation plan

Updated: 2026-09-04

## Current state

The workspace initially contained only the 84-section product specification plus an existing local
AgentMemory plugin installation and a separate private backup Git checkout. The workspace root was
not itself a Git repository. There was no AutoDev application code, dependency manifest, test suite,
database migration, Docker stack, CI workflow, frontend, or project documentation.

The existing `/.agents`, `/plugins`, and `/memory-github-sync` trees are operational user
infrastructure, not AutoDev source. They are preserved and excluded from the new root repository.

Installed tools discovered during bootstrap:

- Codex CLI `0.151.0-alpha.7.2`, including App Server schema generation;
- `uv 0.11.7` (Python 3.13 was not yet installed at discovery time);
- Git `2.53.0.windows.3`;
- Docker Engine/Compose `29.2.1` / `v5.0.2`;
- Node `24.13.1`; Ollama was not available on `PATH`.

## Gap analysis

| Area | Initial state | Required outcome |
|---|---|---|
| Foundation | Missing | Python package, API, worker, config, Docker, CI |
| Durable data | Missing | PostgreSQL models/migrations; Redis ephemeral only |
| State control | Missing | Strict Project and Task FSMs with negative tests |
| Execution | Missing | Transactional scheduler and restart-safe attempts |
| AI routing | Missing | Local-first task-aware router, quotas, health, fallback |
| Coding agent | Missing | Version-isolated Codex App Server adapter and test server |
| Delivery loop | Missing | Goal through verified task commit and COMPLETED |
| Git | Missing | Safe subprocess service, branches/worktrees/commit/merge/push |
| QA/review | Missing | Deterministic checks, typed review, Playwright artifacts |
| Memory | External service exists | Replaceable MCP/HTTP AgentMemory adapter and lifecycle use |
| Deployment | Missing | Staging, health checks, approval policy, deterministic rollback |
| UI/analytics | Missing | Observable dashboard, events, metrics, benchmarking |

## Architectural decisions and deviations

1. AutoDev uses the workspace root while explicitly ignoring the pre-existing AgentMemory trees.
   This keeps the supplied specification at the project root without importing private memory data.
2. The first architecture is a modular monolith plus worker, matching the specification. No Kafka,
   Kubernetes, Temporal, or service mesh is introduced.
3. Python 3.13 remains the declared target. Bootstrap installs a managed 3.13 interpreter because
   the host initially exposed 3.14/3.12 but not 3.13.
4. Integration boundaries are typed Protocols. CI fakes exercise the same orchestration contracts;
   production adapters remain present and runtime-selectable.
5. External API assumptions are isolated. Codex schemas are generated from the installed CLI rather
   than copied into core models.

## Milestones and dependency order

### M0 — repository and developer foundation (verified)

Tasks: root safety ignores, Python package, config, Docker services, CI, docs, constitution, status.

Done when install, lint, types, unit tests, API health, and configuration safety defaults pass.

### M1 — durable orchestration foundation (verified)

Tasks: SQLAlchemy models, Alembic migration, Project/Task FSMs, audit append service, dependency DAG,
transactional PostgreSQL claim using `FOR UPDATE SKIP LOCKED`, retry limits, recovery rules.

Done when unit/negative tests pass and PostgreSQL integration proves exclusive claims and recovery.

### M2 — first complete vertical slice (verified)

Tasks: goal API, typed planner output, task creation, local route, CodingAgent Protocol, fake worker for
CI, production Codex adapter, fixture repository, deterministic checks, typed review, safe Git commit.

Done when an E2E test changes the fixture, runs tests, records review/check evidence, commits with a
task link, and transitions the task/project to COMPLETED. A failed check must enter a bounded fix loop.

Evidence: the default suite has 61 passing tests (one PostgreSQL test is gated by its connection
environment variable), and the gated test passes against the local PostgreSQL container. The live
database is migrated through revision `20260903_0003`, including JSONB document fields. Ruff and
strict mypy pass. Codex App Server initialization and AgentMemory health/search were also exercised
against the locally installed services without starting a paid model turn or writing memory.

### M3 — local and provider AI reliability (verified)

Tasks: Ollama manager, LiteLLM/generic OpenAI adapter, provider registry, all requested provider
profiles, privacy routing, quota ledger/snapshots, cooldown/circuit breaker, structured-output repair.

Done when 429, timeout, invalid JSON, unavailable model, budget, privacy, and offline tests prove safe
fallback without paid use.

Evidence: provider configuration accepts Ollama, LiteLLM, named cloud gateways, LM Studio, and a
generic OpenAI-compatible endpoint without storing secret values. Durable quota, usage, health,
cooldown, prompt version, header reset parsing, 429 and timeout fallback, unavailable local models,
structured repair, privacy, and zero-paid-budget behavior are covered by automated tests.

### M4 — Git, review, memory, and repository intelligence (verified)

Tasks: branch/worktree lifecycle, conflict detection, repo map/context builder, secret redaction and
scan, local/cloud review policy, AgentMemory MCP/HTTP adapter, decision/experience/incident records.

Done when temp-repository integration tests and AgentMemory contract tests pass without leaking source
or secrets.

Evidence: deterministic repository mapping and scoped/redacted context assembly feed execution with
read-only AgentMemory retrieval. Codex thread/turn identifiers persist for retry continuity. Git tests
cover managed worktrees, scoped commits, clone, fast-forward merge, tags, revert, staged-change
protection, path escape rejection, conflict reporting, and automatic merge abort.

### M5 — QA and deployment lifecycle (verified)

Tasks: check discovery, Playwright runner/artifacts, staging adapters, CI status, health/readiness,
approval gates, rollback and incident creation.

Done when deterministic browser/API smoke tests pass and forced health failure performs and records a
rollback; no real production target is touched by tests.

Evidence: deterministic discovery covers Python, JavaScript, Go, and Rust checks. A Playwright CLI
runner snapshots before reference actions and captures console, requests, screenshots, and traces;
the real CLI opened the local FastAPI docs, found the service title, observed zero console errors and
HTTP 200 for OpenAPI, and saved ignored artifacts under `output/playwright`. Deployment adapters cover
controlled Docker Compose, GitHub Actions workflow dispatch/status, and generic webhooks. Production
preconditions and approvals are enforced before any adapter call; forced verification failure tests
prove deterministic rollback, redacted logs, an incident record, and a QA-failure-to-fix-task path.

### M6 — concurrency and operator experience (verified)

Tasks: parallel dependency-aware workers/worktrees, event streaming, CLI/doctor, React dashboard,
metrics, model benchmark history, model tournament, production autonomy policy.

Done when parallel non-conflicting tasks merge safely, conflicts become fix tasks, the UI reflects DB
state, and all V1 acceptance criteria have traceable automated evidence.

Evidence: a runnable host worker releases completed dependencies, performs concurrent PostgreSQL
claims, renews leases, recovers crashes, and executes coding in isolated task worktrees. Integration
is serialized; branches that started behind main are rebased and their checks rerun before a
fast-forward merge. The operator API supports pause/resume, retry/cancel, priority and policy-safe
model override, approvals, audit, provider/model usage, memory search, and Prometheus metrics. The
React control room production image passed desktop/mobile Playwright smoke with WebSocket connected,
HTTP 200 data requests, and zero console errors. The final suite is 106 passing tests plus the
separately passing real-PostgreSQL concurrency test; the full Compose stack is healthy and migration
revision `20260903_0006` applied successfully.

### M7 — native VS Code and editable model runtime (verified)

Tasks: native VS Code activity-bar extension, secure OpenRouter settings, persistent provider/model
catalog, Ollama discovery, per-role model selection, worker wiring, Windows Ollama bootstrap outside
the system drive, and refreshed operator documentation.

Done when the VSIX builds and installs, encrypted credentials cannot be read back, model discovery
and selection pass positive/negative integration tests, migration `20260903_0007` applies to the
live PostgreSQL stack, and an installed local model is visible through the host and containerized API.

Evidence: VSIX 0.2.3 is installed and activates in VS Code; the production dashboard exposes
OpenRouter settings and an explicit local-model picker. Ollama 0.33.2, its model root, and its logon
task live on `D:`. `qwen2.5-coder:7b` returned the exact inference smoke marker at 100% GPU, while
`qwen3-embedding:0.6b` returned one 1024-dimensional vector at 100% GPU. Both were discovered through
the containerized API and persisted as the implementation and embedding preferences. The final
default suite is 130 passing tests plus the separately passing PostgreSQL concurrency test; Ruff,
strict mypy, both TypeScript checks, Docker health, and the Playwright zero-console-error smoke pass.

### M7.1 — safe project and task removal (verified)

Project runs and individual tasks can be deleted from both the dashboard and the native VS Code
control surface after explicit confirmation. Active execution is rejected until the project is
paused or the task is cancelled and its worker attempt has stopped. Runtime records cascade while
audit and model-usage history remain retained without dangling project/task references. API success,
missing-resource, active-run, and cascade behavior are covered by integration tests; a temporary
project was created and removed through the production-container dashboard without leaving test data.

### M7.2 — independent task pause and resume (verified)

An individual non-terminal task can be paused and resumed from the API, dashboard, or native VS Code
control surface without changing the project state or stopping sibling tasks. Pausing an executing
task preserves its paused state, discards the in-flight result, and waits for the worker attempt to
stop before allowing resume. FSM, scheduler isolation, active-attempt safety, worker discard, and
invalid-transition behavior are covered by integration and unit tests. A production-container
browser smoke also confirmed `READY → PAUSED → READY` while the project stayed `READY`.

## Cross-cutting completion criteria

Every completed milestone requires implementation, positive and failure tests, passing Ruff/mypy,
updated migration where relevant, updated docs/status, a reviewed scoped diff, no high-severity open
finding, and a logical task-linked commit. Secrets, generated junk, and the existing memory backup
must never enter Git.
