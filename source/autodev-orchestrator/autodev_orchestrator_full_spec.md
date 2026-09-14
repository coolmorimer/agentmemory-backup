# Autonomous Dev Orchestrator
## Полное техническое задание и архитектура

**Версия документа:** 1.0  
**Дата:** 2026-09-03  
**Рабочее название:** AutoDev Orchestrator  
**Назначение:** автономное управление разработкой программных проектов от исходной цели до production deployment.

---

# 1. Концепция проекта

AutoDev Orchestrator — локально управляемая автономная система разработки, которая принимает от пользователя высокоуровневую цель, самостоятельно превращает её в архитектуру и backlog, распределяет задачи между AI-моделями и Codex, управляет репозиторием, запускает тесты, выполняет browser QA, делает commit/push, запускает CI/CD, проверяет staging/production и сохраняет накопленный инженерный опыт между проектами.

Пользователь должен иметь возможность дать системе запрос уровня:

> Создай CRM для сервиса оборудования. Backend FastAPI, frontend React. Нужны клиенты, заявки, оборудование, роли, Telegram-уведомления, Docker и production deployment.

После этого система должна максимально автономно выполнить полный жизненный цикл проекта, останавливаясь только на действительно критических policy-gates, если они включены.

---

# 2. Главная цель

Создать автономного AI Tech Lead / Project Manager / DevOps Orchestrator, способного:

1. принять исходную цель;
2. исследовать существующий repository;
3. создать/актуализировать техническую архитектуру;
4. сформировать milestones, epics, tasks и dependency graph;
5. выбирать оптимальную AI-модель для каждой задачи;
6. использовать локальные AI-модели;
7. использовать несколько внешних AI providers;
8. использовать Codex как основной coding/execution agent;
9. запускать несколько Codex workers параллельно в git worktrees;
10. автоматически запускать unit/integration/e2e тесты;
11. анализировать ошибки и создавать fix tasks;
12. выполнять независимый code review;
13. управлять git branch/commit/rebase/merge/push;
14. запускать CI/CD;
15. деплоить staging;
16. выполнять browser/API smoke testing;
17. при разрешённой политике деплоить production;
18. автоматически выполнять rollback при неуспешном healthcheck;
19. вести общую память проектов через AgentMemory;
20. переиспользовать решения и опыт между проектами;
21. работать при временной недоступности облачных AI providers;
22. минимизировать расход внешних бесплатных квот;
23. поддерживать прозрачный audit log всех решений и действий.

---

# 3. Основные принципы

## 3.1. LLM не является источником истины

Состояние проекта, задач, запусков, тестов и deployment хранится в PostgreSQL.

LLM только:
- предлагает решения;
- классифицирует;
- планирует;
- анализирует;
- ревьюит;
- создаёт машинно-читаемые результаты.

LLM не должен хранить единственную копию важного состояния в контексте диалога.

## 3.2. Deterministic validation > мнение модели

Успех задачи определяется прежде всего:
- exit code;
- unit tests;
- integration tests;
- linters;
- type checks;
- contract tests;
- Playwright;
- healthchecks;
- CI status;
- policy engine.

Фраза AI «всё готово» не считается доказательством.

## 3.3. Local-first для рутины

Простые задачи сначала отправляются локальным моделям.

Облачный free tier используется для:
- сложного reasoning;
- архитектуры;
- независимого review;
- задач, с которыми локальная модель не справилась.

Codex используется для:
- фактической реализации;
- сложного debugging;
- refactoring;
- выполнения команд;
- работы с repository.

## 3.4. Provider-agnostic architecture

Оркестратор не должен зависеть от конкретного AI API.

Все модели вызываются через единый gateway и собственный Model Router.

## 3.5. Безопасность production

LLM не получает production credentials в prompt.

Production deployment выполняется через CI/CD или ограниченный deployment adapter.

Секреты должны передаваться только инфраструктуре выполнения.

## 3.6. Воспроизводимость

Каждое значимое действие должно оставлять:
- task run;
- prompt metadata;
- model/provider;
- git SHA;
- test report;
- deployment record;
- decision log;
- memory checkpoint.

---

# 4. Целевое железо для локального AI

Основной профиль рабочей станции:

- GPU: NVIDIA RTX 3060 12 GB VRAM
- RAM: 24 GB
- OS: Windows 11 как основной desktop
- Docker Desktop / WSL2 допустимы
- VS Code используется как UI разработчика, но не является обязательным execution layer

Система должна быть работоспособна на этом железе.

---

# 5. Локальные AI-модели

Основной runtime: **Ollama**.

Также должен существовать OpenAI-compatible adapter для LM Studio и других локальных серверов.

## 5.1. Рекомендуемый основной пул

### qwen2.5-coder:7b

Роль:
- быстрый анализ логов;
- классификация ошибок;
- summarization;
- простой code review;
- генерация memory records;
- описание git diff;
- быстрые вспомогательные coding tasks.

Профиль:
- fast;
- low VRAM;
- используется по умолчанию для дешёвых задач.

### qwen2.5-coder:14b

Роль:
- основной локальный code reviewer;
- debugging среднего уровня;
- анализ небольших/средних diff;
- локальный coding fallback.

Это основной local coding model для RTX 3060 12 GB.

### qwen3:14b

Роль:
- reasoning;
- планирование;
- анализ архитектурных проблем;
- классификация сложных incidents;
- локальный fallback planner.

### gemma3:12b

Роль:
- vision;
- анализ screenshots;
- UI QA;
- сравнение ожидаемого и фактического интерфейса;
- мультимодальный анализ.

### deepseek-coder-v2:16b

Роль:
- альтернативный локальный code reviewer;
- независимое второе мнение;
- debugging.

### qwen3-embedding:0.6b

Роль:
- online embeddings;
- быстрый AgentMemory recall;
- semantic search по коротким memory chunks.

### qwen3-embedding:4b

Роль:
- background repository indexing;
- cross-project retrieval;
- reindex;
- более качественный semantic search.

## 5.2. Опциональные тяжёлые модели

Не использовать как always-on по умолчанию:

- gpt-oss:20b;
- devstral:24b;
- qwen3-coder:30b.

Они могут использовать CPU/GPU offload и запускаться только для тяжёлых локальных задач.

## 5.3. Ограничения local runtime

На RTX 3060 12 GB:
- одновременно держать не более одной крупной 12–16B модели;
- embedding model может быть отдельным небольшим процессом;
- использовать короткий рабочий context там, где возможно;
- большие repository не передавать целиком;
- использовать repo-map + RAG + memory retrieval.

Пример целевых context limits:

```yaml
local_context_policy:
  qwen2_5_coder_7b: 32768
  qwen2_5_coder_14b: 16384
  qwen3_14b: 16384
  gemma3_12b: 16384
  deepseek_coder_v2_16b: 16384
  heavy_models: 8192
```

Значения должны быть конфигурируемыми.

---

# 6. Облачные AI providers

Система не должна быть привязана только к OpenRouter.

Поддержать adapters минимум для:

1. OpenRouter
2. Groq
3. Google Gemini
4. NVIDIA NIM
5. Mistral
6. Cloudflare Workers AI
7. SambaNova
8. Cerebras
9. Fireworks
10. Hugging Face Inference Providers
11. OpenAI-compatible generic endpoint
12. Ollama
13. LM Studio / local OpenAI-compatible endpoint

Опционально:
- Together;
- DeepInfra;
- другие OpenAI-compatible providers.

## 6.1. Важное требование

Не хардкодить бесплатные лимиты в приложении.

Free/trial limits меняются.

Система должна:
- хранить статические fallback limits в config;
- читать rate-limit response headers, если provider их возвращает;
- учитывать 429;
- учитывать reset time;
- вести собственный usage ledger;
- позволять вручную задать quota profile;
- периодически обновлять provider health.

## 6.2. Бесплатный режим по умолчанию

```yaml
budget:
  allow_paid_models: false
  max_cloud_cost_usd_day: 0.0
  max_cloud_cost_usd_month: 0.0
```

Paid fallback включается пользователем отдельно.

---

# 7. AI Gateway

Использовать два уровня.

## 7.1. LiteLLM Proxy

LiteLLM отвечает за:
- единый OpenAI-compatible API;
- provider adapters;
- authentication;
- logging;
- cost tracking;
- базовые retries;
- базовые fallbacks;
- rate limiting.

## 7.2. Custom Model Router

Собственный Python Model Router находится выше LiteLLM и принимает интеллектуальное решение о маршруте.

```text
Orchestrator
     |
Custom Model Router
     |
LiteLLM Proxy
     |
Providers / Ollama
```

Custom Router не должен быть заменён стандартным LiteLLM router, потому что системе требуется task-aware routing.

---

# 8. Model Router

## 8.1. Вход

```json
{
  "task_type": "code_review",
  "complexity": 0.61,
  "context_tokens_estimate": 6500,
  "private": true,
  "requires_tools": false,
  "requires_vision": false,
  "requires_structured_output": true,
  "project_id": "uuid",
  "task_id": "uuid"
}
```

## 8.2. Model profile

```yaml
id: ollama/qwen2.5-coder:14b

capabilities:
  coding: 0.82
  reasoning: 0.72
  review: 0.86
  planning: 0.55
  vision: false
  tool_calling: false
  structured_output: true

privacy:
  local: true
  private_code_allowed: true

runtime:
  expected_latency: 12.0
  max_context: 16384

cost:
  billing_mode: local
```

Cloud example:

```yaml
id: groq/example-model

capabilities:
  coding: 0.88
  reasoning: 0.90
  review: 0.87
  structured_output: true

privacy:
  local: false
  private_code_allowed: false

cost:
  billing_mode: free
```

## 8.3. Scoring

Первоначальная формула:

```text
score =
  quality_score       * 0.30 +
  task_match          * 0.25 +
  reliability         * 0.15 +
  quota_score         * 0.10 +
  latency_score       * 0.10 +
  privacy_score       * 0.10
```

Веса должны быть конфигурируемыми.

## 8.4. Escalation

```text
local-fast
   |
confidence low / failed
   v
local-main
   |
failed
   v
free-cloud
   |
failed
   v
strong-cloud
   |
implementation needed
   v
Codex
```

Для security/payment/migration задач допускается model tournament.

## 8.5. Circuit breaker

При повторных:
- 429;
- timeout;
- 5xx;
- invalid response;
- auth error;

provider/model переводится в состояния:

```text
HEALTHY
DEGRADED
COOLDOWN
DISABLED
```

Cooldown должен иметь exponential backoff + jitter.

---

# 9. Codex integration

Codex — основной implementation/execution agent.

Основной способ интеграции: **Codex App Server**.

Не управлять Codex через клики по VS Code.

VS Code остаётся UI наблюдения.

## 9.1. Codex App Server adapter

Сервис должен:
- запускать `codex app-server`;
- выполнять initialize handshake;
- создавать threads;
- запускать turns;
- слушать streaming events;
- обрабатывать item events;
- собирать agent messages;
- собирать command execution;
- собирать file changes / diff;
- поддерживать approvals;
- поддерживать retry при перегрузке app-server;
- восстанавливать thread после restart.

Протокол Codex App Server должен инкапсулироваться в отдельном adapter.

При запуске dev environment автоматически генерировать локально актуальную schema:

```bash
codex app-server generate-json-schema --out ./generated/codex
```

или TypeScript schema при необходимости.

Не копировать protocol schema вручную.

## 9.2. Codex worker

Каждый worker получает:
- project path;
- worktree path;
- task;
- acceptance criteria;
- relevant memory;
- project constitution;
- commands allowed;
- test commands;
- completion contract.

Worker не должен сам менять task status напрямую.

Он возвращает structured result.

Пример:

```json
{
  "status": "completed",
  "summary": "Implemented order creation",
  "changed_files": [
    "app/api/orders.py"
  ],
  "tests_run": [
    "pytest tests/orders -q"
  ],
  "tests_passed": true,
  "risks": [],
  "follow_up_tasks": []
}
```

---

# 10. Parallel Codex workers

Использовать Git worktrees.

Пример:

```text
/repo
/worktrees/TASK-101
/worktrees/TASK-102
/worktrees/TASK-103
```

Scheduler должен запускать параллельно только задачи, которые не имеют unresolved dependencies.

По умолчанию:

```yaml
workers:
  max_codex_workers: 2
  max_local_gpu_workers: 1
  max_cloud_workers: 4
```

Настройки зависят от железа и квот.

Перед merge:
1. rebase/merge target branch;
2. resolve conflict через отдельную fix task;
3. запустить required checks;
4. code review;
5. merge.

---

# 11. Project lifecycle

Основной state machine проекта:

```text
CREATED
RESEARCHING
PLANNING
READY
IMPLEMENTING
TESTING
REVIEWING
STAGING
VERIFYING_STAGING
DEPLOYING
VERIFYING_PRODUCTION
COMPLETED
BLOCKED
FAILED
PAUSED
```

Task states:

```text
DRAFT
READY
RUNNING
WAITING_DEPENDENCY
TESTING
REVIEWING
FIX_REQUIRED
APPROVED
COMPLETED
BLOCKED
FAILED
CANCELLED
```

Transitions должны быть строго валидированы Python state machine.

---

# 12. Goal → backlog

Пользователь создаёт Project Goal.

Planner обязан создать:

1. assumptions;
2. risks;
3. architecture;
4. milestones;
5. epics;
6. tasks;
7. dependencies;
8. acceptance criteria;
9. tests;
10. deploy requirements.

Пример task:

```json
{
  "key": "TASK-006",
  "title": "Implement order creation",
  "type": "backend",
  "priority": 70,
  "risk": "medium",
  "depends_on": [
    "TASK-004",
    "TASK-005"
  ],
  "acceptance_criteria": [
    "POST /orders creates an order",
    "unknown product returns 404",
    "stock reservation is transactional",
    "duplicate request is idempotent"
  ],
  "required_checks": [
    "pytest tests/orders -q",
    "ruff check .",
    "mypy app"
  ]
}
```

---

# 13. Project Constitution

Каждый managed project должен иметь:

```text
.agent/constitution.md
.agent/project.yaml
.agent/status.md
.agent/decisions/
```

`constitution.md` содержит неизменяемые без явного решения правила проекта.

Пример:

```markdown
# Project Constitution

- Python >= 3.13.
- Every public API requires tests.
- Every DB schema change requires migration.
- Secrets must never be committed.
- Production is changed only through CI/CD.
- Do not disable tests to make the build green.
- Do not remove validations without an explicit decision.
- Destructive migrations require a backup/approval gate.
```

---

# 14. AgentMemory

Использовать AgentMemory как общий memory layer.

Интеграция должна быть через adapter, чтобы implementation можно было заменить.

Поддержать:
- MCP;
- HTTP API;
- optional hooks.

Не связывать core orchestration напрямую с конкретным npm package API.

## 14.1. Типы памяти

### GLOBAL

Общие знания:
- preferred libraries;
- coding conventions;
- reusable patterns;
- infrastructure patterns;
- solved bugs;
- known incompatibilities.

### PROJECT

- architecture;
- API contracts;
- database design;
- deployment;
- infrastructure;
- naming;
- limitations.

### DECISION

ADR-style:

```text
Problem
Decision
Reason
Alternatives
Consequences
Project
Date
Related commits
```

### EXPERIENCE

```text
Problem
Symptoms
Root cause
Fix
Prevention
Reusable
```

### INCIDENT

```text
Environment
Failure
Logs summary
Cause
Rollback
Fix
Postmortem
```

## 14.2. Что не хранить

Не использовать AgentMemory как копию repository.

Не сохранять:
- большие source files;
- node_modules;
- build artifacts;
- бинарные файлы;
- полные секреты;
- каждый stdout без сжатия.

Исходный код читается из Git repository.

## 14.3. Retrieval

Перед сложной task:

```text
task
 -> local embedding
 -> semantic memory search
 -> top relevant memories
 -> context builder
 -> Codex/LLM
```

## 14.4. Memory consolidation

Сырые события периодически сжимаются локальной моделью.

Сохраняются только полезные:
- decisions;
- errors;
- patterns;
- fixes;
- conventions.

---

# 15. Repository intelligence

Создать Repo Intelligence subsystem.

Он должен:
- определить языки;
- определить framework;
- найти package manifests;
- найти test configuration;
- определить entrypoints;
- определить migrations;
- определить Docker;
- определить CI;
- построить repo map;
- найти README/AGENTS.md/CLAUDE.md;
- найти TODO/FIXME;
- найти generated directories.

Использовать deterministic parsing там, где возможно.

Опционально:
- tree-sitter;
- AST;
- ripgrep;
- language-specific parsers.

Не использовать LLM для задачи, которую можно надёжно решить parser/grep.

---

# 16. Context Builder

Каждому AI запросу передавать минимально необходимый контекст.

Context Builder собирает:

```text
task
+
acceptance criteria
+
project constitution
+
repo map fragments
+
relevant source snippets
+
relevant memory
+
related test output
+
previous attempt summary
```

Не передавать весь repository автоматически.

---

# 17. QA subsystem

## 17.1. Static checks

Python:
- Ruff;
- mypy/pyright при наличии;
- formatting;
- dependency validation.

JS/TS:
- ESLint;
- TypeScript;
- formatter;
- package tests.

## 17.2. Unit tests

Framework определяется repository intelligence.

## 17.3. Integration tests

Поднимать зависимости через Docker Compose/Testcontainers там, где требуется.

## 17.4. Browser QA

Использовать Playwright.

Browser worker должен уметь:
- открыть приложение;
- дождаться ready;
- пройти основные flows;
- заполнять формы;
- делать screenshots;
- проверять console errors;
- проверять failed network requests;
- проверять HTTP status;
- сохранять trace.

При падении:
- создать QA finding;
- приложить screenshot;
- приложить trace/log summary;
- создать fix task.

## 17.5. Visual QA

Screenshot может анализироваться локальной `gemma3:12b`.

Vision model не заменяет assertions Playwright.

---

# 18. Review pipeline

После implementation:

```text
Codex
  ->
deterministic checks
  ->
local reviewer
  ->
cloud reviewer if needed
  ->
approval
```

## 18.1. Local review first

qwen2.5-coder:14b или deepseek-coder-v2:16b.

## 18.2. Escalate when

- high-risk task;
- reviewer confidence low;
- auth;
- payment;
- database migration;
- security;
- deployment;
- large diff;
- repeated failure;
- reviewer found severe issue.

## 18.3. Review contract

```json
{
  "approved": false,
  "confidence": 0.91,
  "issues": [
    {
      "severity": "high",
      "file": "app/orders/service.py",
      "line": 81,
      "problem": "stock update is not atomic",
      "required_fix": "use one transaction and row lock"
    }
  ]
}
```

---

# 19. Model tournament

Для high-risk decisions допускается 2–3 независимых reviewer models.

Пример:

```text
Diff
 -> local reviewer
 -> provider A reviewer
 -> provider B reviewer
 -> judge / deterministic policy
```

Не применять tournament для low-risk изменений.

---

# 20. Git subsystem

Поддержать:

- repository initialization;
- clone;
- branch;
- worktree;
- status;
- diff;
- commit;
- rebase;
- merge;
- push;
- tags;
- rollback;
- GitHub PR optional.

Commit format:

```text
feat(orders): add transactional stock reservation

Task: TASK-128
Checks: pytest, ruff, mypy
Review: approved
```

Каждый commit привязывается к task.

---

# 21. GitHub integration

Минимально:
- push;
- branch protection awareness;
- CI status;
- GitHub Actions;
- optional PR creation;
- optional issue linking.

Credentials не передаются модели.

Для API использовать GitHub App или fine-grained token с минимальными scope.

---

# 22. CI/CD

Production deployment не выполнять через произвольный SSH, если можно использовать CI/CD.

Recommended flow:

```text
git push
 -> GitHub Actions
 -> build
 -> test
 -> image
 -> staging deploy
 -> smoke
 -> production deploy
 -> healthcheck
```

## 22.1. Deployment adapter interface

Поддержать минимум:
- docker-compose over controlled remote executor;
- GitHub Actions deployment;
- generic webhook deployment.

Позже:
- Kubernetes;
- Nomad;
- cloud providers.

---

# 23. Production policy

Конфигурация:

```yaml
autonomy:
  code: auto
  tests: auto
  review: auto
  git_commit: auto
  git_push: auto

  staging:
    deploy: auto

  production:
    deploy: require_approval

  migrations:
    safe: auto
    destructive: require_approval

  secrets:
    expose_to_models: false
```

Поддержать `production.deploy: auto`.

Однако auto production возможен только если:
- CI green;
- staging green;
- smoke tests green;
- healthcheck defined;
- rollback mechanism configured;
- no unresolved high severity findings.

---

# 24. Rollback

После production:

1. health endpoint;
2. readiness;
3. smoke tests;
4. container/process state;
5. optionally error metrics.

Если verification failed:

```text
rollback
 -> incident
 -> collect logs
 -> create fix task
 -> memory incident
```

Rollback должен быть deterministic.

---

# 25. Secrets

Секреты:
- `.env` не отправляется LLM;
- значения маскируются в logs;
- model prompts получают placeholder;
- credentials доступны execution layer;
- secret scanner перед commit.

Минимум:
- detect common token patterns;
- block accidental `.env`;
- redact Authorization headers;
- redact API keys.

---

# 26. Command execution security

Создать Command Policy Engine.

Категории:

```text
READ_ONLY
BUILD
TEST
PACKAGE_INSTALL
GIT_SAFE
GIT_WRITE
NETWORK
DEPLOY
DESTRUCTIVE
UNKNOWN
```

Правила конфигурируемые.

Пример запрещённых без policy:
- disk formatting;
- arbitrary destructive filesystem command;
- production database deletion;
- credential dump;
- disabling security tools.

Codex App Server approvals должны маппиться на policy engine.

---

# 27. Database

PostgreSQL является source of truth.

Использовать pgvector для internal semantic index, если это требуется рядом с AgentMemory.

Redis:
- ephemeral cache;
- distributed locks;
- pub/sub;
- rate-limit/cache;
- provider cooldown.

Не использовать Redis как единственную durable task queue.

---

# 28. Durable scheduler

Tasks выбираются из PostgreSQL.

Пример паттерна:

```sql
SELECT *
FROM tasks
WHERE status = 'READY'
AND next_run_at <= now()
ORDER BY priority DESC, created_at
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

Worker claim должен быть transactional.

Это позволяет переживать restart процесса без потери task state.

---

# 29. Основные таблицы

```text
projects
goals
project_settings

milestones
epics
tasks
task_dependencies
task_attempts
task_artifacts

agents
agent_runs

codex_threads
codex_turns
codex_events

model_providers
models
model_capabilities
model_health
model_usage
quota_snapshots

memory_links
decisions

git_repositories
git_worktrees
git_commits
pull_requests

test_runs
test_results
qa_findings

deployments
deployment_checks
incidents

audit_events
approvals
```

---

# 30. Task schema

Основные поля:

```text
id UUID
project_id UUID
key VARCHAR
title
description
type
status
priority
risk
complexity
privacy_level
assigned_agent
parent_epic_id
acceptance_criteria JSONB
required_checks JSONB
context_requirements JSONB
attempt_count
max_attempts
next_run_at
created_at
updated_at
completed_at
```

---

# 31. Provider quota tracking

Таблица должна хранить:

```text
provider
model
window
requests_used
requests_remaining
tokens_used
tokens_remaining
reset_at
source
updated_at
```

`source`:
- headers;
- manual;
- API;
- estimated.

Router не должен считать неизвестный limit бесконечным.

---

# 32. Observability

Минимум:
- structured JSON logging;
- correlation ID;
- project ID;
- task ID;
- agent run ID;
- model call ID.

Добавить:
- OpenTelemetry;
- Prometheus metrics;
- optional Grafana.

Метрики:
- task success rate;
- average attempts;
- provider latency;
- provider error rate;
- 429;
- model quality score;
- test failures;
- Codex turn duration;
- deployment success;
- rollback count;
- local GPU utilization optional.

---

# 33. Self-benchmarking

Каждый model call должен сохранять:

```text
provider
model
task_type
task_complexity
latency
tokens
status
error
review_score
downstream_success
cost
```

Позже Model Router строит empirical score.

Пример:

```text
qwen14 code_review       84%
provider_x code_review   92%
provider_y planning      95%
```

Не менять routing weights автоматически без ограничений.

В первой версии использовать rolling statistics.

---

# 34. Web dashboard

Backend:
- FastAPI.

Frontend:
- React;
- TypeScript;
- Vite.

Основные экраны:

## Projects

- project;
- progress;
- current state;
- task counts;
- staging/prod;
- active workers.

## Project

- goal;
- architecture;
- milestones;
- task graph;
- active tasks;
- activity timeline;
- tests;
- deployments.

## Task

- input;
- attempts;
- Codex output;
- diff;
- test runs;
- reviews;
- memory used;
- commits.

## Models

- providers;
- health;
- quota;
- latency;
- success rate;
- current route;
- cooldown.

## Memory

- search;
- project memory;
- global memory;
- decisions;
- incidents.

## Approvals

- production deploy;
- destructive migration;
- dangerous command;
- secret-requiring action.

---

# 35. Backend API

Минимальный API:

```text
POST   /api/projects
GET    /api/projects
GET    /api/projects/{id}

POST   /api/projects/{id}/goals
POST   /api/projects/{id}/plan
POST   /api/projects/{id}/start
POST   /api/projects/{id}/pause
POST   /api/projects/{id}/resume

GET    /api/projects/{id}/tasks
GET    /api/tasks/{id}
POST   /api/tasks/{id}/retry
POST   /api/tasks/{id}/cancel

GET    /api/providers
GET    /api/providers/health
GET    /api/models
GET    /api/model-usage

GET    /api/deployments
POST   /api/deployments/{id}/approve

GET    /api/approvals
POST   /api/approvals/{id}/approve
POST   /api/approvals/{id}/reject

GET    /api/memory/search
GET    /api/audit
```

WebSocket/SSE:
- live project events;
- Codex execution;
- test events;
- deployment events.

---

# 36. Suggested repository structure

```text
autodev-orchestrator/
|
|-- apps/
|   |-- api/
|   |   |-- autodev/
|   |   |   |-- main.py
|   |   |   |-- config.py
|   |   |   |
|   |   |   |-- api/
|   |   |   |-- db/
|   |   |   |-- models/
|   |   |   |-- schemas/
|   |   |   |
|   |   |   |-- orchestration/
|   |   |   |   |-- engine.py
|   |   |   |   |-- project_fsm.py
|   |   |   |   |-- task_fsm.py
|   |   |   |   |-- scheduler.py
|   |   |   |   |-- planner.py
|   |   |   |   |-- recovery.py
|   |   |   |
|   |   |   |-- routing/
|   |   |   |   |-- router.py
|   |   |   |   |-- scoring.py
|   |   |   |   |-- escalation.py
|   |   |   |   |-- circuit_breaker.py
|   |   |   |
|   |   |   |-- providers/
|   |   |   |   |-- base.py
|   |   |   |   |-- litellm.py
|   |   |   |   |-- local.py
|   |   |   |
|   |   |   |-- codex/
|   |   |   |   |-- app_server.py
|   |   |   |   |-- protocol.py
|   |   |   |   |-- worker.py
|   |   |   |   |-- thread_store.py
|   |   |   |
|   |   |   |-- memory/
|   |   |   |   |-- base.py
|   |   |   |   |-- agentmemory.py
|   |   |   |   |-- retrieval.py
|   |   |   |   |-- consolidation.py
|   |   |   |
|   |   |   |-- repo/
|   |   |   |   |-- intelligence.py
|   |   |   |   |-- map.py
|   |   |   |   |-- context_builder.py
|   |   |   |
|   |   |   |-- git/
|   |   |   |   |-- repository.py
|   |   |   |   |-- worktrees.py
|   |   |   |   |-- github.py
|   |   |   |
|   |   |   |-- qa/
|   |   |   |   |-- checks.py
|   |   |   |   |-- tests.py
|   |   |   |   |-- playwright.py
|   |   |   |   |-- review.py
|   |   |   |
|   |   |   |-- deploy/
|   |   |   |   |-- base.py
|   |   |   |   |-- github_actions.py
|   |   |   |   |-- docker_remote.py
|   |   |   |   |-- health.py
|   |   |   |   |-- rollback.py
|   |   |   |
|   |   |   |-- security/
|   |   |   |   |-- command_policy.py
|   |   |   |   |-- secrets.py
|   |   |   |   |-- redaction.py
|   |   |   |
|   |   |   |-- telemetry/
|   |   |       |-- logging.py
|   |   |       |-- metrics.py
|   |   |
|   |   |-- tests/
|   |   |-- alembic/
|   |   |-- pyproject.toml
|   |
|   |-- web/
|       |-- src/
|       |-- package.json
|       |-- vite.config.ts
|
|-- services/
|   |-- worker/
|   |-- playwright-runner/
|
|-- config/
|   |-- models.yaml
|   |-- providers.yaml.example
|   |-- policies.yaml
|   |-- routing.yaml
|
|-- docker/
|-- scripts/
|-- docs/
|   |-- architecture.md
|   |-- providers.md
|   |-- deployment.md
|   |-- memory.md
|   |-- security.md
|
|-- generated/
|   |-- codex/
|
|-- .agent/
|   |-- constitution.md
|   |-- project.yaml
|   |-- status.md
|
|-- docker-compose.yml
|-- docker-compose.dev.yml
|-- .env.example
|-- Makefile
|-- README.md
|-- AGENTS.md
```

---

# 37. Python stack

Target:
- Python 3.13;
- FastAPI;
- Pydantic v2;
- SQLAlchemy 2 async;
- Alembic;
- asyncpg;
- httpx;
- tenacity;
- structlog;
- Redis client;
- pgvector;
- OpenTelemetry;
- pytest;
- pytest-asyncio;
- Ruff;
- mypy.

Не добавлять framework без необходимости.

---

# 38. Frontend stack

- React;
- TypeScript;
- Vite;
- TanStack Query;
- React Router;
- simple component library;
- WebSocket/SSE client.

Frontend не является blocker для backend MVP.

---

# 39. Docker development environment

`docker-compose.dev.yml`:

- PostgreSQL + pgvector;
- Redis;
- LiteLLM;
- AgentMemory;
- API;
- worker;
- frontend;
- optional observability.

Ollama может запускаться на Windows host и пробрасываться в Docker через configurable URL.

---

# 40. Configuration

Все параметры через:
- environment;
- YAML;
- database settings.

Приоритет:
1. DB project override;
2. environment;
3. YAML default.

Файлы:

```text
config/models.yaml
config/providers.yaml
config/routing.yaml
config/policies.yaml
```

---

# 41. Provider configuration example

```yaml
providers:

  ollama:
    enabled: true
    base_url: http://host.docker.internal:11434
    billing_mode: local

  openrouter:
    enabled: false
    api_key_env: OPENROUTER_API_KEY
    billing_mode: free

  groq:
    enabled: false
    api_key_env: GROQ_API_KEY
    billing_mode: free

  gemini:
    enabled: false
    api_key_env: GEMINI_API_KEY
    billing_mode: free

  nvidia:
    enabled: false
    api_key_env: NVIDIA_API_KEY
    billing_mode: free

  mistral:
    enabled: false
    api_key_env: MISTRAL_API_KEY
    billing_mode: free
```

Ни один secret не должен попадать в git.

---

# 42. Initial routing policy

```yaml
routes:

  log_analysis:
    preferred:
      - ollama/qwen2.5-coder:7b
      - ollama/qwen2.5-coder:14b
      - cloud/free-fast

  code_review:
    preferred:
      - ollama/qwen2.5-coder:14b
      - ollama/deepseek-coder-v2:16b
      - cloud/free-code-review

  planning:
    preferred:
      - ollama/qwen3:14b
      - cloud/free-reasoning

  vision:
    preferred:
      - ollama/gemma3:12b
      - cloud/free-vision

  embeddings:
    preferred:
      - ollama/qwen3-embedding:0.6b

  repository_reindex:
    preferred:
      - ollama/qwen3-embedding:4b
```

Cloud aliases разрешаются Model Router динамически.

---

# 43. Failure handling

Каждая task имеет `max_attempts`.

После ошибки:

1. deterministic classifier;
2. local model analysis;
3. retry if transient;
4. alternate model/provider;
5. Codex fix attempt;
6. external reviewer;
7. mark BLOCKED после лимита.

Never infinite loop.

Пример:

```yaml
recovery:
  task_max_attempts: 5
  same_strategy_max_attempts: 2
  provider_retry_max: 2
```

---

# 44. Loop detection

Система должна обнаруживать:
- повтор одного и того же diff;
- повтор одинаковой ошибки;
- последовательность revert/reapply;
- одинаковый failed test после N попыток;
- бесконечные planner replans.

После detection:
- stop current approach;
- create incident;
- escalate model;
- при необходимости запросить approval/user input.

---

# 45. Human interaction

Несмотря на автономность, пользователь должен иметь возможность:
- pause project;
- cancel task;
- edit backlog;
- override model;
- approve prod;
- approve destructive operation;
- retry;
- provide new goal;
- change priority.

Новая user instruction имеет приоритет над старым планом.

---

# 46. Event bus

События:

```text
project.created
plan.created
task.ready
task.started
codex.turn.started
codex.item
task.tests.started
task.tests.failed
task.review.completed
task.completed
git.commit.created
git.push.completed
deployment.started
deployment.failed
deployment.completed
incident.created
provider.cooldown
memory.updated
```

Для MVP можно использовать internal async event bus + PostgreSQL audit.

Redis Pub/Sub используется для live UI.

---

# 47. Audit log

Каждое действие:

```json
{
  "event": "git.push",
  "project_id": "...",
  "task_id": "...",
  "actor": "orchestrator",
  "agent": "codex-worker-1",
  "timestamp": "...",
  "metadata": {}
}
```

Audit log append-only на application layer.

---

# 48. API structured outputs

Planner/reviewer/router prompts должны использовать Pydantic JSON schemas.

Если provider не поддерживает native structured output:
- просить JSON;
- валидировать Pydantic;
- repair один раз;
- затем fallback provider/model.

Никогда не парсить critical data регулярным выражением из свободного текста, если можно требовать schema.

---

# 49. Testing самого Orchestrator

## Unit

- state transitions;
- scoring;
- provider selection;
- circuit breaker;
- quotas;
- command policy;
- redaction;
- task dependency resolution.

## Integration

- PostgreSQL scheduler;
- Redis;
- LiteLLM mocked providers;
- AgentMemory adapter;
- Codex app-server adapter using fake JSON-RPC server;
- git temp repository;
- worktree operations.

## E2E

Создать fixture project:

```text
examples/todo-api
```

Goal:

```text
Add tags to todo items with tests.
```

AutoDev должен:
1. plan;
2. create task;
3. execute worker (mock in CI, optional real Codex locally);
4. run tests;
5. review;
6. commit;
7. complete.

## Failure E2E

Провайдер возвращает:
- 429;
- timeout;
- invalid JSON.

Router должен переключить маршрут.

---

# 50. Mocks

Тесты CI не должны требовать платных API.

Создать fake OpenAI-compatible provider.

Записанные real provider fixtures не должны содержать secrets/private code.

---

# 51. Minimum viable product

## MVP-0

Foundation:
- FastAPI;
- DB;
- models;
- migrations;
- project/task FSM;
- Docker;
- tests.

## MVP-1

Single project:
- Goal;
- planner;
- backlog;
- scheduler;
- one local model;
- one cloud provider adapter;
- model routing.

## MVP-2

Codex:
- app-server adapter;
- one Codex worker;
- task execution;
- diff;
- tests;
- task completion.

## MVP-3

Memory:
- AgentMemory adapter;
- retrieval;
- project memory;
- decision memory;
- consolidation.

## MVP-4

Git:
- branches;
- worktrees;
- commit;
- push;
- task/commit linking.

## MVP-5

QA:
- local reviewer;
- cloud escalation;
- Playwright;
- screenshots;
- QA findings.

## MVP-6

Multi-provider:
- LiteLLM;
- OpenRouter;
- Groq;
- Gemini;
- NVIDIA;
- Mistral;
- provider health;
- quotas;
- circuit breaker.

## MVP-7

Deployment:
- staging;
- healthcheck;
- rollback;
- CI/CD integration.

## MVP-8

Parallel:
- dependency scheduler;
- multiple Codex worktrees;
- conflict handling.

## V1

- dashboard;
- analytics;
- model benchmarking;
- model tournament;
- production autonomy policies;
- incident workflows.

---

# 52. Acceptance criteria V1

Проект считается V1-ready, если:

1. пользователь создаёт project и goal через API/UI;
2. planner создаёт валидный task DAG;
3. scheduler автоматически выбирает READY task;
4. local/cloud Model Router выбирает доступную модель;
5. 429 одного provider не останавливает проект;
6. отсутствующий cloud internet не ломает local task execution;
7. Codex worker выполняет coding task в worktree;
8. tests запускаются автоматически;
9. failed tests создают fix cycle;
10. независимый reviewer может отклонить diff;
11. task merge происходит только после required checks;
12. commit привязан к task;
13. push работает;
14. staging deployment запускается;
15. Playwright smoke test проходит;
16. failed healthcheck вызывает rollback;
17. memory recall передаёт релевантный опыт в новую task;
18. cross-project memory retrieval работает;
19. secrets не попадают в model logs;
20. audit history позволяет восстановить причины каждого significant action;
21. проект переживает restart backend без потери task state;
22. UI показывает актуальное состояние проекта;
23. production auto deployment отключаем/включаем policy;
24. ни один task не может бесконечно retry;
25. система имеет documented local setup.

---

# 53. Definition of Done для каждой task

Task нельзя помечать COMPLETED, пока:

- acceptance criteria выполнены;
- required checks выполнены;
- отсутствуют unresolved high severity findings;
- diff соответствует task scope;
- generated artifacts не содержат secrets;
- memory summary создан при необходимости;
- task result сохранён.

---

# 54. Performance goals

MVP:
- API response для обычных CRUD < 500 ms;
- task scheduler latency < 2 sec;
- provider fallback < 5 sec плюс фактический provider timeout policy;
- live events latency < 2 sec;
- restart recovery без ручного восстановления state.

AI inference latency не входит в обычный API latency SLO.

---

# 55. Data privacy

Project имеет:

```text
PUBLIC
PRIVATE
LOCAL_ONLY
```

Routing:

- PUBLIC: разрешены configured cloud providers.
- PRIVATE: только providers с `private_code_allowed=true` + local.
- LOCAL_ONLY: только local providers/Codex local repository execution.

Пользователь может переопределять правила provider privacy.

---

# 56. Initial development defaults

Для данной рабочей станции:

```yaml
hardware_profile:
  gpu: RTX_3060_12GB
  ram_gb: 24

runtime:
  max_codex_workers: 2
  max_local_gpu_inference: 1

models:
  fast_local: ollama/qwen2.5-coder:7b
  code_local: ollama/qwen2.5-coder:14b
  reasoning_local: ollama/qwen3:14b
  vision_local: ollama/gemma3:12b
  alternative_code_local: ollama/deepseek-coder-v2:16b
  embedding_fast: ollama/qwen3-embedding:0.6b
  embedding_quality: ollama/qwen3-embedding:4b

budget:
  allow_paid_models: false
  max_cloud_cost_usd_day: 0
```

---

# 57. Development rules for implementation agent

При реализации AutoDev:

1. Сначала сделать foundation, затем AI.
2. Не начинать с dashboard.
3. Не писать огромный монолитный `orchestrator.py`.
4. Каждый subsystem должен иметь interface/protocol.
5. External provider должен иметь adapter.
6. AgentMemory должен иметь adapter.
7. Codex должен иметь adapter.
8. Git должен иметь service layer.
9. Deployment должен иметь adapter.
10. Все state transitions тестируются.
11. Все migrations версионируются.
12. `.env.example` содержит только names/placeholders.
13. Ни один API key не коммитится.
14. README обновляется по мере реализации.
15. Не отключать failing tests ради green CI.
16. Не использовать mock вместо production implementation вне test code.
17. Не оставлять critical TODO после завершения milestone.
18. Перед каждым milestone запускать полный regression suite.

---

# 58. First implementation milestone

Первый реально работающий вертикальный slice:

```text
POST goal
 -> planner
 -> task created
 -> scheduler
 -> local model route
 -> fake/real Codex adapter
 -> file change in fixture repo
 -> pytest
 -> review
 -> commit
 -> task completed
```

Начать именно с этого, а не с одновременной реализации всех providers.

---

# 59. Recommended implementation order

1. repository bootstrap;
2. config;
3. database;
4. domain models;
5. FSM;
6. scheduler;
7. audit;
8. local Ollama adapter;
9. Model Router;
10. generic OpenAI/LiteLLM adapter;
11. planner;
12. Codex App Server adapter;
13. single Codex worker;
14. Git;
15. tests/review;
16. AgentMemory;
17. provider plugins;
18. quotas/circuit breaker;
19. Playwright;
20. staging deployment;
21. rollback;
22. parallel workers;
23. dashboard;
24. advanced benchmarking.

---

# 60. Do not overengineer early

Не добавлять на старте:
- Kubernetes;
- Kafka;
- Temporal;
- service mesh;
- multi-region;
- отдельный microservice для каждого модуля.

Архитектура MVP:
- modular monolith API;
- separate worker process;
- PostgreSQL;
- Redis;
- LiteLLM;
- AgentMemory;
- Ollama.

Позже подсистемы можно вынести.

---

# 61. External interfaces

Все integration adapters должны иметь Protocol/ABC.

Пример:

```python
class LLMProvider(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse: ...
    async def health(self) -> ProviderHealth: ...


class MemoryProvider(Protocol):
    async def search(self, query: MemoryQuery) -> list[MemoryItem]: ...
    async def store(self, item: MemoryItem) -> str: ...


class CodingAgent(Protocol):
    async def run_task(self, task: CodingTask) -> CodingResult: ...


class DeploymentProvider(Protocol):
    async def deploy(self, release: Release) -> DeploymentResult: ...
    async def rollback(self, deployment_id: str) -> DeploymentResult: ...
```

---

# 62. Documentation deliverables

К V1 должны существовать:

```text
README.md
docs/architecture.md
docs/local-models.md
docs/providers.md
docs/codex.md
docs/memory.md
docs/security.md
docs/deployment.md
docs/troubleshooting.md
docs/adding-provider.md
docs/adding-model.md
docs/adding-deployment-adapter.md
```

---

# 63. CLI

Помимо UI/API добавить CLI:

```bash
autodev project create
autodev project start <id>
autodev project pause <id>
autodev status <id>
autodev tasks <id>
autodev models
autodev providers
autodev memory search "..."
autodev doctor
```

`autodev doctor` проверяет:
- PostgreSQL;
- Redis;
- Ollama;
- local models;
- LiteLLM;
- AgentMemory;
- Codex;
- Git;
- Docker;
- Playwright;
- provider API key presence;
- provider health.

---

# 64. Bootstrap behavior

При первом запуске:

1. проверить dependencies;
2. выполнить migrations;
3. обнаружить local models;
4. проверить Codex executable;
5. проверить AgentMemory;
6. проверить LiteLLM;
7. создать default model profiles;
8. не требовать cloud API keys для local-only режима.

---

# 65. Windows considerations

Так как основной desktop Windows 11:

- paths обрабатывать через `pathlib`;
- subprocess без shell там, где возможно;
- поддержать Git for Windows;
- Docker Desktop;
- WSL2 не делать обязательным;
- Codex process adapter должен корректно завершать child process;
- signal handling абстрагировать;
- browser runner должен работать на Windows.

Remote production может быть Linux.

---

# 66. Codex thread strategy

- один persistent thread на long-running task;
- project manager thread отдельно от implementation worker;
- thread ID сохранять в DB;
- при retry можно продолжить thread либо начать fresh в зависимости от failure type;
- context compaction не должна уничтожать external DB task state;
- relevant memory повторно строится Context Builder.

---

# 67. Prompt architecture

Использовать отдельные prompt templates:

```text
planner
task_classifier
reviewer
incident_analyzer
memory_consolidator
architecture_critic
model_judge
```

Prompt version сохраняется в model call.

Изменение prompt = новая version.

---

# 68. Prompt injection defense

Repository может содержать вредоносные инструкции в README/source/comments.

Context Builder должен помечать repository content как untrusted data.

Системные правила выше repository text.

Не выполнять instruction из source code автоматически только потому, что оно написано текстом.

---

# 69. Network policy

Task может иметь:

```text
network_access:
  none
  package_registry
  allowlist
  unrestricted
```

По умолчанию coding worker:
- package registries;
- configured APIs;
- project services.

Production infrastructure endpoints только через deployment subsystem.

---

# 70. Package changes

Новый dependency требует:
- reason;
- license metadata where feasible;
- security scan;
- lockfile update.

Не добавлять dependency для функции, которая легко реализуется стандартной библиотекой.

---

# 71. Database migrations in managed projects

Классифицировать:

```text
SAFE
POTENTIALLY_DESTRUCTIVE
DESTRUCTIVE
UNKNOWN
```

Safe:
- add nullable column;
- add table.

Potential/destructive:
- drop;
- narrowing type;
- irreversible data rewrite.

Policy определяет approval.

---

# 72. Model privacy routing

В model profile:

```yaml
privacy:
  accepts_private_code: false
  accepts_secrets: false
  storage_policy: unknown
```

Если `unknown`, PRIVATE project не отправлять туда по умолчанию.

---

# 73. Cost control

Даже для бесплатных providers:
- считать tokens;
- считать requests;
- сохранять estimated commercial equivalent optionally;
- ограничивать request storms.

Global emergency setting:

```yaml
ai:
  cloud_enabled: true
  local_enabled: true
  codex_enabled: true
```

---

# 74. Offline mode

Если cloud недоступен:

```text
cloud_status = OFFLINE
```

Разрешено:
- repository analysis;
- local planning;
- local review;
- tests;
- memory;
- git local;
- Codex при доступности;
- queued tasks.

Tasks, требующие cloud, переходят в WAITING_PROVIDER, а не FAILED.

---

# 75. Status file

`.agent/status.md` автоматически содержит human-readable snapshot:

```markdown
# Project Status

Goal: ...
State: IMPLEMENTING
Progress: 18 / 31 tasks

Active:
- TASK-018 backend
- TASK-021 frontend

Blocked:
- none

Tests:
- 341 passed
- 0 failed

Staging:
- healthy

Production:
- v0.3.1
```

DB остаётся source of truth.

---

# 76. AGENTS.md

Корневой `AGENTS.md` самого AutoDev должен объяснять coding agents:

- architecture;
- commands;
- test requirements;
- directories;
- prohibited shortcuts;
- current milestone.

Он должен быть коротким и поддерживаемым.

---

# 77. Initial commands

Желаемый DX:

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up -d postgres redis litellm
uv sync
uv run alembic upgrade head
uv run autodev doctor
uv run fastapi dev apps/api/autodev/main.py
```

Frontend отдельно:

```bash
cd apps/web
npm install
npm run dev
```

Точные команды могут быть адаптированы при реализации.

---

# 78. References to verify during implementation

Так как внешние API быстро меняются, implementation agent обязан перед использованием конкретного protocol/provider сверяться с актуальной официальной документацией.

Особенно:
- Codex App Server schema должна генерироваться локальной версией Codex;
- LiteLLM provider configuration;
- AgentMemory MCP/HTTP integration;
- provider model IDs;
- free tier limits;
- Ollama model names.

Не зашивать в core assumptions, которые можно получить runtime/config.

---

# 79. Final product behavior example

Пользователь:

> Создай сервис бронирования СТО. Backend FastAPI, React frontend, PostgreSQL, ЮKassa, Telegram, Docker. Деплой на production после staging.

AutoDev:

1. создаёт project;
2. исследует пустой/существующий repo;
3. recall cross-project memory;
4. создаёт архитектуру;
5. создаёт task DAG;
6. выполняет independent architecture review;
7. запускает Codex worker;
8. тестирует;
9. исправляет;
10. делает review;
11. commit;
12. push;
13. выполняет следующие tasks параллельно;
14. поднимает staging;
15. Playwright проходит user flows;
16. healthcheck;
17. при policy auto — production;
18. проверяет production;
19. сохраняет decisions/experience;
20. помечает goal COMPLETE.

Пользователь может наблюдать весь процесс в dashboard, но не обязан вручную вести задачи.

---

# 80. Итоговая архитектурная схема

```text
                         USER
                           |
                     PROJECT GOAL
                           |
                           v
                  +------------------+
                  |   ORCHESTRATOR   |
                  +---------+--------+
                            |
                 +----------+-----------+
                 |                      |
                 v                      v
            AgentMemory              TASK DAG
                 |                      |
                 |                      v
                 |               Durable Scheduler
                 |                      |
                 |                      v
                 |                MODEL ROUTER
                 |                      |
       +---------+------------+---------+---------+
       |                      |                   |
       v                      v                   v
   LOCAL AI              FREE CLOUD             CODEX
   Ollama                LiteLLM                App Server
       |                      |                   |
 Qwen/Gemma           OpenRouter/Groq        implementation
 DeepSeek              Gemini/NVIDIA         execution
 embeddings            Mistral/etc.          debugging
       |                      |                   |
       +----------------------+-------------------+
                              |
                              v
                        Git Worktree
                              |
                         deterministic
                            checks
                              |
                 +------------+------------+
                 |                         |
                 v                         v
             Reviewer                  Playwright
                 |                         |
                 +------------+------------+
                              |
                              v
                             Git
                              |
                              v
                         GitHub / CI
                              |
                              v
                           Staging
                              |
                         smoke / e2e
                              |
                              v
                         Production
                              |
                       health / rollback
                              |
                              v
                        Memory Update
                              |
                              v
                          NEXT TASK
```

---

# 81. Critical success criterion

Система считается успешной не тогда, когда умеет написать код, а когда умеет **надёжно довести долгоживущий проект через повторяющийся цикл plan → implement → verify → review → integrate → deploy → learn**, переживая ошибки моделей, провайдеров, тестов и отдельных worker processes без потери project state.

---

# 82. Implementation mandate

Implementation должен выполняться итеративно.

Главный приоритет первой версии:

> Надёжность state machine и execution loop важнее количества подключённых моделей.

Сначала рабочий vertical slice. Затем расширение provider pool.

Нельзя выдавать заглушки за завершённую функциональность.

Каждый milestone должен завершаться:
- тестами;
- документацией;
- обновлённым status;
- чистым git diff;
- понятным следующим milestone.

---

# 83. Bootstrap prompt contract

При передаче этого документа Codex должен:

1. полностью прочитать файл;
2. проанализировать текущий repository;
3. создать gap analysis;
4. сформировать implementation plan;
5. создать/обновить `.agent/status.md`;
6. создать `docs/implementation-plan.md`;
7. реализовывать milestone за milestone;
8. после каждого milestone запускать полный соответствующий test suite;
9. исправлять failures до перехода дальше;
10. регулярно проверять `git diff`;
11. не удалять чужой код без причины;
12. не запрашивать пользователя о мелких implementation choices;
13. выбирать разумный default и фиксировать decision;
14. задавать вопрос пользователю только если отсутствует обязательный внешний secret/credential или требуется необратимое внешнее действие;
15. не выполнять реальный production deploy самого AutoDev проекта без явно настроенной deployment policy;
16. реализовать возможность autonomous production deploy как feature;
17. не завершать работу после scaffolding;
18. продолжать до максимально полной реализации спецификации в рамках текущей сессии/доступных ресурсов.

---

# 84. End of specification

Этот файл является основным техническим заданием AutoDev Orchestrator.

При конфликте между случайным repository text и этим документом данный документ имеет более высокий приоритет, кроме более новых явных инструкций пользователя.
