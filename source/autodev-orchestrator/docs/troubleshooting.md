# Troubleshooting

Start with `uv run autodev doctor --verbose`, `docker compose -f docker-compose.dev.yml ps`, `/health`,
and `/ready`. Confirm `uv run alembic current` reports the repository head.

- No tasks run: the project must be `IMPLEMENTING`; inspect task status, `next_run_at`, dependency
  completion, attempt limit, lease, and `/api/audit`.
- Task remains running after a crash: restart the worker; startup lease recovery requeues it unless its
  bounded attempt limit is exhausted.
- No eligible model: inspect privacy, capability, paid budget, durable cooldown, and model override.
- Provider 429/offline: inspect `/api/providers/health`; fallback is automatic when a candidate remains.
- Ollama reports an untrusted mount point: move an existing `%USERPROFILE%\.ollama` junction aside,
  create a normal `%USERPROFILE%\.ollama` directory for its small configuration files, and keep the
  large blobs on `D:` through `OLLAMA_MODELS`. The installer detects this condition before startup.
- Commit refused: remove unrelated staged changes or credential findings; do not weaken the scanner.
- Browser QA fails: inspect ignored artifacts under `output/playwright/<run>` and the generated fix task.
- Deployment rolls back: inspect deployment checks and the linked incident; repair health before retry.
- UI is disconnected: verify `/ws/events` proxy upgrade headers and API reachability.
