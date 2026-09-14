# AutoDev Orchestrator agent guide

AutoDev is a Python 3.13 modular monolith: FastAPI API, durable PostgreSQL-backed scheduler,
provider/coding-agent adapters, and a separate worker entrypoint. PostgreSQL is authoritative;
Redis is ephemeral only.

## Commands

- Install: `uv sync --all-groups`
- Tests: `uv run pytest`
- Lint: `uv run ruff check .`
- Types: `uv run mypy apps/api/autodev`
- Migrate: `uv run alembic upgrade head`
- API: `uv run uvicorn autodev.main:app --reload`

## Rules

- Test every state transition and significant failure path.
- Require deterministic checks before marking tasks complete.
- Keep integrations behind Protocols; test fakes belong under tests.
- Never send secrets or `.env` values to models or logs.
- Never use shell command concatenation with user input.
- Do not edit `/.agents`, `/plugins`, or `/memory-github-sync`; they predate AutoDev.
- Do not perform a real production deployment without explicit configured policy and credentials.

Current milestone: M7 complete — native VS Code control room, encrypted provider settings, and
live Ollama model selection on the Windows host.
