# V1 acceptance evidence

Status is based on executable evidence in this repository as of 2026-09-04. “Live” means a local
runtime smoke was also performed; no cloud or production target was changed.

| # | Criterion | Status | Evidence |
|---:|---|---|---|
| 1 | Project and goal through API/UI | Verified | `test_projects_api.py`; responsive control-room browser smoke |
| 2 | Planner creates valid DAG | Verified | `test_goal_execution.py`, planner validation tests |
| 3 | Scheduler selects READY | Verified | `test_scheduler.py`; PostgreSQL gated test |
| 4 | Local/cloud route selection | Verified | `test_router.py`, provider configuration tests |
| 5 | 429 does not stop project | Verified | `test_provider_reliability.py` |
| 6 | Cloud outage does not break fallback | Verified | timeout fallback integration test |
| 7 | Coding agent changes repository | Verified | goal-to-commit E2E; Codex App Server contract test |
| 8 | Automatic tests | Verified | goal-to-commit E2E and check discovery tests |
| 9 | Failed tests create bounded fix cycle | Verified | engine failure E2E and QA evidence test |
| 10 | Reviewer can reject diff | Verified | review/engine failure tests |
| 11 | Merge/commit only after checks | Verified | engine E2E and Git integration tests |
| 12 | Commit linked to task | Verified | `GitCommit` assertion in goal E2E |
| 13 | Push works | Verified | local remote push integration test |
| 14 | Staging deployment starts | Verified | deployment coordinator/adapter tests |
| 15 | Playwright smoke passes | Live verified | API docs and control room: requests 200, console errors 0, screenshots captured |
| 16 | Failed health check rolls back | Verified | forced rollback deployment test |
| 17 | Relevant memory reaches task | Verified | goal E2E context assertion |
| 18 | Cross-project/global retrieval | Verified | goal E2E project plus global retrieval |
| 19 | Secrets excluded | Verified | redaction, scanner, Git, deployment incident tests |
| 20 | Audit explains significant actions | Verified | API, scheduler, deployment, control tests |
| 21 | Restart retains task state | Verified | PostgreSQL source, migrations, lease recovery tests |
| 22 | UI shows current state | Live verified | desktop/mobile browser snapshots and WebSocket connection |
| 23 | Production autonomy is policy controlled | Verified | require-approval and auto-policy tests |
| 24 | No infinite task retry | Verified | FSM, max attempts, lease recovery and explicit retry tests |
| 25 | Local setup documented | Verified | README plus architecture/runbooks |

## Operator-integration addendum

| Capability | Status | Evidence |
|---|---|---|
| Native VS Code control surface | Live verified | installed VSIX 0.2.3; project/task actions; TypeScript check |
| Independent task pause/resume | Live verified | task FSM/API/worker integration tests; dashboard pause/resume smoke; sibling scheduling remains active |
| Safe project/task deletion | Live verified | API cascade/active-run tests; web confirmation smoke; audit retention |
| OpenRouter configuration without plaintext readback | Verified | encrypted database record and API integration test |
| Ollama discovery and explicit local-model choice | Live verified | coder and embedding discovered/selected through container API; dashboard shows selected coder |
| Local binaries and models stay off `C:` | Live verified | `D:\Apps\Ollama`; `D:\AI\Ollama\models`; persisted `OLLAMA_MODELS`; logon task |
| Real local inference | Live verified | exact coder smoke response and 1024-dimensional embedding; both reported 100% GPU |

Cloud credentials are intentionally absent until the operator enters one, and paid-model defaults
remain disabled. OpenRouter's authenticated call cannot be live-verified without that operator key.
