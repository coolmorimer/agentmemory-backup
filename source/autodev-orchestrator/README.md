# AutoDev Orchestrator

AutoDev Orchestrator is a local-first, policy-aware system that turns a high-level project goal
into a durable task graph and drives implementation, deterministic QA, review, Git integration,
deployment, recovery, and engineering memory.

The current implementation is under active construction from
[`autodev_orchestrator_full_spec.md`](autodev_orchestrator_full_spec.md). PostgreSQL is the source
of truth; Redis is used only for ephemeral coordination.

## Development setup

Requirements: Python 3.13, `uv`, Git, and Docker Desktop.

```powershell
Copy-Item .env.example .env
docker compose -f docker-compose.dev.yml up -d postgres redis
uv sync --all-groups
uv run alembic upgrade head
uv run pytest
uv run uvicorn autodev.main:app --reload
# In another terminal, start the durable task worker:
uv run autodev-worker
```

In a second terminal, run the operator UI:

```powershell
Set-Location apps/web
npm install
npm run dev
```

Or build API and dashboard together with
`docker compose -f docker-compose.dev.yml --profile application up --build` and open
`http://127.0.0.1:5173`.

## VS Code integration

AutoDev ships a native workspace extension in `apps/vscode`. It adds an **AutoDev** activity-bar
container with the Control Room, projects, provider/model state, local-model selection, goal
creation, worker controls, and an OpenRouter setup command. Package and install it locally with:

```powershell
Set-Location apps/vscode
npm ci
npm run package
code --install-extension .\autodev-orchestrator-vscode-0.2.3.vsix --force
```

The checked-in `.vscode` configuration keeps the official Codex extension in native Windows mode
and adds tasks for the AutoDev stack, worker, doctor, and Ollama discovery. Reload the VS Code
window once after first installing the VSIX.

## Local and OpenRouter models

Run `scripts/bootstrap-secrets.ps1` before saving provider API keys. The generated master key stays
only in the ignored `.env`; provider keys entered in the dashboard or VS Code are encrypted in
PostgreSQL and are never returned by the API.

On this Windows workstation Ollama is installed outside `C:` and keeps model blobs outside `C:`:

```powershell
.\scripts\install-ollama.ps1
.\scripts\bootstrap-local-models.ps1 -Install -Profile minimal `
  -OllamaExecutable D:\Apps\Ollama\ollama.exe
```

Use **Settings → AI providers and local models** in the dashboard, or the matching AutoDev commands
in VS Code, to configure/test OpenRouter, discover installed Ollama models, and choose the local
implementation advisor. Codex remains the tool-enabled repository executor; the selected model
contributes bounded implementation advice and its usage is recorded.

API liveness and readiness are available at `http://127.0.0.1:8000/health` and `/ready`; OpenAPI is
available at `/docs`.

Implemented runtime layers now include transactional task claims, the Codex App Server adapter,
local/cloud provider routing with durable quota and cooldown state, scoped AgentMemory retrieval,
repository intelligence, managed Git worktrees, deterministic checks/review, Playwright CLI QA, and
approval-gated deployment adapters with rollback and incidents.

Operator commands include `autodev project create`, `project start|pause|resume`, `status`, `tasks`,
`models`, `providers`, `memory-search`, and `doctor`. The same daily controls are exposed in the
VS Code activity bar. See the
[V1 acceptance matrix](docs/acceptance-matrix.md) and [architecture](docs/architecture.md) for the
evidence map and subsystem boundaries.

## Safety defaults

- Paid models are disabled.
- Daily and monthly cloud budgets are zero.
- Production deployment requires approval.
- Unknown providers cannot receive private code.
- Secrets are not included in model context or logs.
- Task commits are blocked when the staged diff contains a `.env` file or a common credential token.

Existing AgentMemory installation and backup directories in this workspace are excluded from the
AutoDev repository and are not modified by the project.
