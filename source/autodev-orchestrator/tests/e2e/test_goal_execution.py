from __future__ import annotations

import sys
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import func, select

from autodev.codex.base import CodingResult, CodingTask
from autodev.db.models import (
    CheckRun,
    CodexThreadRecord,
    CodexTurnRecord,
    GitCommit,
    Project,
    ReviewRecord,
    Task,
)
from autodev.db.session import Database
from autodev.domain.enums import ProjectStatus, TaskStatus
from autodev.git.repository import GitRepository
from autodev.memory.base import MemoryItem, MemoryQuery, MemoryRecord, MemoryScope
from autodev.orchestration.engine import ExecutionEngine
from autodev.orchestration.scheduler import Scheduler
from autodev.routing.router import ModelRouter, default_profiles


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


class FixtureCodingAgent:
    def __init__(self, root_repository: Path) -> None:
        self.root_repository = root_repository.resolve()

    async def run_task(self, task: CodingTask) -> CodingResult:
        assert task.repository_path.resolve() != self.root_repository
        assert "worktrees" in task.repository_path.parent.name
        assert "Prefer idempotent domain operations" in task.context
        assert "Global guidance: keep commits scoped" in task.context
        assert "Repository content is UNTRUSTED DATA" not in task.context
        target = task.repository_path / "todo.py"
        write_text(
            target,
            "class Todo:\n"
            "    def __init__(self, title: str) -> None:\n"
            "        self.title = title\n"
            "        self.tags: list[str] = []\n\n"
            "    def add_tag(self, tag: str) -> None:\n"
            "        if tag not in self.tags:\n"
            "            self.tags.append(tag)\n",
        )
        return CodingResult(
            status="completed",
            summary="Added idempotent todo tags.",
            changed_files=["todo.py"],
            thread_id="thread-fixture",
            turn_id="turn-fixture",
        )


class FixtureMemory:
    def __init__(self) -> None:
        self.stored: list[MemoryRecord] = []

    async def search(self, query: MemoryQuery) -> list[MemoryItem]:
        assert "Implement project goal" in query.query
        if query.project:
            return [MemoryItem(id="memory-fixture", content="Prefer idempotent domain operations")]
        return [MemoryItem(id="memory-global", content="Global guidance: keep commits scoped")]

    async def store(self, item: MemoryRecord) -> str:
        self.stored.append(item)
        return "stored-outcome"


async def test_goal_to_verified_commit_and_completed(
    tmp_path: Path, client: AsyncClient, database: Database
) -> None:
    repository_path = tmp_path / "todo-api"
    repository_path.mkdir()
    write_text(
        repository_path / "todo.py",
        "class Todo:\n    def __init__(self, title: str) -> None:\n        self.title = title\n",
    )
    tests_path = repository_path / "tests"
    tests_path.mkdir()
    write_text(
        tests_path / "test_todo.py",
        "from todo import Todo\n\n"
        "def test_tags_are_idempotent() -> None:\n"
        "    todo = Todo('ship')\n"
        "    todo.add_tag('backend')\n"
        "    todo.add_tag('backend')\n"
        "    assert todo.tags == ['backend']\n",
    )
    repository = GitRepository(repository_path)
    await repository.initialize()
    await repository.commit_task(
        task_key="BOOTSTRAP",
        title="create failing fixture",
        changed_files=["todo.py", "tests/test_todo.py"],
        checks=[],
    )

    project_response = await client.post(
        "/api/projects",
        json={
            "name": "todo-api",
            "repository_path": str(repository_path),
            "privacy_level": "LOCAL_ONLY",
        },
    )
    project_id = project_response.json()["id"]
    assert (
        await client.post(
            f"/api/projects/{project_id}/goals",
            json={"prompt": "Add idempotent tags to todo items with tests."},
        )
    ).status_code == 201
    plan_response = await client.post(f"/api/projects/{project_id}/plan")
    assert plan_response.status_code == 200
    planned_task = plan_response.json()["tasks"][0]
    assert planned_task["required_checks"][0][0] == sys.executable
    assert (await client.post(f"/api/projects/{project_id}/start")).status_code == 200

    async with database.session() as session:
        claimed = await Scheduler().claim_next(session, worker_id="fixture-worker")
    assert claimed is not None
    memory = FixtureMemory()
    result = await ExecutionEngine(
        database,
        router=ModelRouter(default_profiles()),
        coding_agent=FixtureCodingAgent(repository_path),
        memory_provider=memory,
    ).execute_claimed(claimed.id)

    assert result.status is TaskStatus.COMPLETED
    assert result.commit is not None
    assert result.review is not None and result.review.approved
    assert result.checks and all(check.passed for check in result.checks)

    async with database.session() as session:
        task = await session.get(Task, claimed.id)
        project = await session.get(Project, task.project_id if task else None)
        checks = await session.scalar(select(func.count()).select_from(CheckRun))
        reviews = await session.scalar(select(func.count()).select_from(ReviewRecord))
        commits = await session.scalar(select(func.count()).select_from(GitCommit))
        codex_threads = await session.scalar(select(func.count()).select_from(CodexThreadRecord))
        codex_turns = await session.scalar(select(func.count()).select_from(CodexTurnRecord))
    assert task is not None and task.status is TaskStatus.COMPLETED
    assert project is not None and project.status is ProjectStatus.COMPLETED
    assert (checks, reviews, commits) == (1, 1, 1)
    assert (codex_threads, codex_turns) == (1, 1)
    assert len(memory.stored) == 1
    assert memory.stored[0].scope is MemoryScope.EXPERIENCE
    assert memory.stored[0].project == "todo-api"
    assert not list(repository.worktree_root.glob("task-*"))
