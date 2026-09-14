# Project Status

Updated: 2026-09-04

Goal: implement the full autonomous plan → implement → verify → review → integrate → deploy → learn loop.

State: COMPLETED

Current milestone: M7 verified; VS Code and editable model runtime complete.

Progress:

- Specification: fully read (84 sections).
- Existing workspace: inventoried and protected.
- Git: root initialization is ready; nested memory backup remains separate and untouched.
- Runtime: PostgreSQL and Redis are healthy under Docker Compose; schema is at revision
  `20260903_0007` with durable provider credentials, discovered models, and per-role routing
  preferences in addition to the V1 records.
- Delivery loop: goal → deterministic plan → transactional claim → coding agent → checks → review →
  Git commit → task/project COMPLETED is covered end to end against a temporary repository.
- Tests: 130 passed and 1 environment-gated PostgreSQL test skipped in the default suite. The gated
  PostgreSQL concurrency test also passes separately against the live local container.
- Quality: Ruff and strict mypy pass.
- Worker: `autodev-worker` performs dependency release, concurrent durable claims, lease heartbeat,
  isolated task worktrees, rebase/recheck integration, crash recovery, and bounded retries.
- Operations: the full Docker Compose application profile is running; migration exited 0, API is
  healthy/ready, and the responsive dashboard is available on port 5173.
- UI: production-container Playwright smoke verified confirmed project deletion without stale-state
  errors; project and task controls support safe stop/delete workflows and independent task pause.
- VS Code: `local-autodev.autodev-orchestrator-vscode` 0.2.3 is installed with an Activity Bar
  control room, provider/model views, goal controls, independent task pause/resume, project/task
  deletion, worker controls, and OpenRouter setup.
- Local AI: Ollama 0.33.2 runs from `D:\Apps\Ollama`, persists blobs under
  `D:\AI\Ollama\models`, and starts at logon through the `AutoDev Ollama` scheduled task.
  `qwen2.5-coder:7b` and `qwen3-embedding:0.6b` are installed and selected; live inference and
  1024-dimensional embedding calls both ran at 100% GPU.
- Acceptance: all 25 V1 criteria are traced in `docs/acceptance-matrix.md`.

Blocked:

- Cloud provider credentials are intentionally optional and absent from source.
- OpenRouter's authenticated live call requires an operator-owned API key; encrypted storage,
  no-readback behavior, health testing, discovery, and failure handling are verified without one.

Optional next iteration:

- Install additional models from the documented `recommended` profile if a specific workload needs
  them; the bootstrap intentionally avoids silently downloading the full multi-gigabyte pool.
- Configure a disposable staging target for a non-mocked deployment rehearsal.
- Add Kubernetes/Temporal only if scale requires decomposition beyond the verified modular monolith.
