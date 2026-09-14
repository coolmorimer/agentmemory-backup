from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from autodev.codex.base import CodingResult, CodingTask
from autodev.db.models import AuditEvent, Project, Task, TaskAttempt, TaskDependency
from autodev.db.session import Database
from autodev.domain.enums import ProjectStatus, TaskStatus
from autodev.orchestration.engine import ExecutionEngine
from autodev.orchestration.scheduler import Scheduler
from autodev.routing.models import RoutingDecision
from autodev.routing.router import ModelRouter, default_profiles


class UnusedCodingAgent:
    async def run_task(self, task: CodingTask) -> CodingResult:
        raise AssertionError(f"coding agent should not run for {task.task_id}")


async def test_project_can_pause_and_resume_from_durable_checkpoint(client: AsyncClient) -> None:
    response = await client.post(
        "/api/projects",
        json={"name": "controlled", "repository_path": "C:/controlled"},
    )
    project_id = response.json()["id"]

    paused = await client.post(f"/api/projects/{project_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "PAUSED"

    resumed = await client.post(f"/api/projects/{project_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "CREATED"


async def test_task_priority_model_override_retry_and_cancel(
    client: AsyncClient, database: Database
) -> None:
    async with database.session() as session:
        project = Project(name="fixture", repository_path="C:/fixture")
        session.add(project)
        await session.flush()
        task = Task(
            project_id=project.id,
            key="CONTROL",
            title="Control me",
            status=TaskStatus.FAILED,
            attempt_count=5,
            max_attempts=5,
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    updated = await client.patch(
        f"/api/tasks/{task_id}",
        json={"priority": 99, "model_override": "codex/app-server"},
    )
    assert updated.status_code == 200
    assert updated.json()["priority"] == 99

    retried = await client.post(f"/api/tasks/{task_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "READY"
    assert retried.json()["max_attempts"] == 6

    cancelled = await client.post(f"/api/tasks/{task_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"

    async with database.session() as session:
        task = await session.get(Task, task_id)
    assert task is not None
    assert task.context_requirements["model_override"] == "codex/app-server"


async def test_pausing_one_task_leaves_project_and_sibling_running(
    client: AsyncClient, database: Database
) -> None:
    async with database.session() as session:
        project = Project(
            name="independent-pause",
            repository_path="C:/independent-pause",
            status=ProjectStatus.IMPLEMENTING,
        )
        session.add(project)
        await session.flush()
        paused_task = Task(
            project_id=project.id,
            key="PAUSE-ME",
            title="Pause only me",
            status=TaskStatus.READY,
            priority=100,
        )
        sibling = Task(
            project_id=project.id,
            key="KEEP-RUNNING",
            title="Keep running",
            status=TaskStatus.READY,
            priority=10,
        )
        session.add_all([paused_task, sibling])
        await session.commit()
        project_id = project.id
        paused_task_id = paused_task.id
        sibling_id = sibling.id

    paused = await client.post(f"/api/tasks/{paused_task_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "PAUSED"

    async with database.session() as session:
        project = await session.get(Project, project_id)
        sibling = await session.get(Task, sibling_id)
    async with database.session() as session:
        claimed = await Scheduler().claim_next(session, worker_id="sibling-worker")
    assert project is not None and project.status is ProjectStatus.IMPLEMENTING
    assert sibling is not None and sibling.status is TaskStatus.READY
    assert claimed is not None and claimed.id == sibling_id

    resumed = await client.post(f"/api/tasks/{paused_task_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "READY"


async def test_running_task_must_finish_stopping_before_resume(
    client: AsyncClient, database: Database
) -> None:
    async with database.session() as session:
        project = Project(name="running-pause", repository_path="C:/running-pause")
        session.add(project)
        await session.flush()
        task = Task(
            project_id=project.id,
            key="RUNNING",
            title="Running task",
            status=TaskStatus.RUNNING,
            claimed_by="worker-1",
        )
        session.add(task)
        await session.flush()
        attempt = TaskAttempt(task_id=task.id, number=1, strategy_key="test")
        session.add(attempt)
        await session.commit()
        task_id = task.id
        attempt_id = attempt.id

    paused = await client.post(f"/api/tasks/{task_id}/pause")
    assert paused.status_code == 200
    assert paused.json()["status"] == "PAUSED"

    still_stopping = await client.post(f"/api/tasks/{task_id}/resume")
    assert still_stopping.status_code == 409
    assert still_stopping.json()["detail"] == (
        "task is still stopping; wait for the worker before resuming it"
    )

    async with database.session() as session, session.begin():
        task = await session.get(Task, task_id)
        attempt = await session.get(TaskAttempt, attempt_id)
        assert task is not None and attempt is not None
        task.claimed_by = None
        task.lease_expires_at = None
        attempt.status = TaskStatus.PAUSED.value
        attempt.finished_at = datetime.now(UTC)

    resumed = await client.post(f"/api/tasks/{task_id}/resume")
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "READY"


async def test_worker_discards_result_when_running_task_was_paused(
    database: Database,
) -> None:
    async with database.session() as session:
        project = Project(name="worker-pause", repository_path="C:/worker-pause")
        session.add(project)
        await session.flush()
        task = Task(
            project_id=project.id,
            key="WORKER-PAUSE",
            title="Worker pause",
            status=TaskStatus.PAUSED,
            attempt_count=1,
            claimed_by="worker-1",
        )
        session.add(task)
        await session.flush()
        attempt = TaskAttempt(task_id=task.id, number=1, strategy_key="test")
        session.add(attempt)
        await session.commit()
        task_id = task.id
        attempt_id = attempt.id

    status = await ExecutionEngine(
        database,
        router=ModelRouter(default_profiles()),
        coding_agent=UnusedCodingAgent(),
    )._persist_result(
        task_id=task_id,
        attempt_number=1,
        route=RoutingDecision(
            model_id="codex/app-server",
            provider="codex",
            score=1,
            reasons=["fixture"],
        ),
        coding=CodingResult(status="interrupted", summary="Paused by operator"),
        checks=[],
        review=None,
        commit=None,
        repository_path=Path("C:/worker-pause"),
    )
    assert status is TaskStatus.PAUSED

    async with database.session() as session:
        task = await session.get(Task, task_id)
        attempt = await session.get(TaskAttempt, attempt_id)
        discarded = await session.scalar(
            select(AuditEvent).where(AuditEvent.event == "task.execution.discarded")
        )
    assert task is not None and task.status is TaskStatus.PAUSED
    assert task.claimed_by is None
    assert attempt is not None and attempt.status == TaskStatus.PAUSED.value
    assert attempt.finished_at is not None
    assert discarded is not None and discarded.details["reason"] == "paused"


async def test_terminal_task_cannot_be_paused_and_ready_task_cannot_be_resumed(
    client: AsyncClient, database: Database
) -> None:
    async with database.session() as session:
        project = Project(name="invalid-pause", repository_path="C:/invalid-pause")
        session.add(project)
        await session.flush()
        completed = Task(
            project_id=project.id,
            key="COMPLETED",
            title="Completed task",
            status=TaskStatus.COMPLETED,
        )
        ready = Task(
            project_id=project.id,
            key="READY",
            title="Ready task",
            status=TaskStatus.READY,
        )
        session.add_all([completed, ready])
        await session.commit()
        completed_id = completed.id
        ready_id = ready.id

    pause_response = await client.post(f"/api/tasks/{completed_id}/pause")
    assert pause_response.status_code == 409
    resume_response = await client.post(f"/api/tasks/{ready_id}/resume")
    assert resume_response.status_code == 409
    assert resume_response.json()["detail"] == "task is not paused"


async def test_task_delete_removes_task_runtime_records_and_preserves_audit(
    client: AsyncClient, database: Database
) -> None:
    async with database.engine.begin() as connection:
        await connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    async with database.session() as session:
        project = Project(name="deletion", repository_path="C:/deletion")
        session.add(project)
        await session.flush()
        task = Task(
            project_id=project.id,
            key="DELETE-ME",
            title="Delete me",
            status=TaskStatus.COMPLETED,
        )
        dependent = Task(
            project_id=project.id,
            key="DEPENDENT",
            title="Dependent task",
            status=TaskStatus.WAITING_DEPENDENCY,
        )
        session.add_all([task, dependent])
        await session.flush()
        attempt = TaskAttempt(
            task_id=task.id,
            number=1,
            strategy_key="test",
            status=TaskStatus.COMPLETED.value,
            finished_at=datetime.now(UTC),
        )
        dependency = TaskDependency(task_id=dependent.id, depends_on_task_id=task.id)
        original_audit = AuditEvent(
            event="task.completed",
            project_id=project.id,
            task_id=task.id,
        )
        session.add_all([attempt, dependency, original_audit])
        await session.commit()
        task_id = task.id
        attempt_id = attempt.id
        dependency_id = dependency.id
        original_audit_id = original_audit.id

    deleted = await client.delete(f"/api/tasks/{task_id}")
    assert deleted.status_code == 204
    assert deleted.content == b""

    async with database.session() as session:
        assert await session.get(Task, task_id) is None
        assert await session.get(TaskAttempt, attempt_id) is None
        assert await session.get(TaskDependency, dependency_id) is None
        preserved_audit = await session.get(AuditEvent, original_audit_id)
        deletion_audit = await session.scalar(
            select(AuditEvent).where(AuditEvent.event == "task.deleted")
        )
    assert preserved_audit is not None
    assert preserved_audit.task_id is None
    assert deletion_audit is not None
    assert deletion_audit.task_id is None
    assert deletion_audit.details["task_id"] == str(task_id)


@pytest.mark.parametrize(
    ("task_status", "claimed_by", "running_attempt"),
    [
        (TaskStatus.RUNNING, "worker-1", False),
        (TaskStatus.READY, "worker-1", False),
        (TaskStatus.CANCELLED, None, True),
    ],
)
async def test_active_task_cannot_be_deleted(
    client: AsyncClient,
    database: Database,
    task_status: TaskStatus,
    claimed_by: str | None,
    running_attempt: bool,
) -> None:
    async with database.session() as session:
        project = Project(name="active", repository_path="C:/active")
        session.add(project)
        await session.flush()
        task = Task(
            project_id=project.id,
            key="ACTIVE",
            title="Active task",
            status=task_status,
            claimed_by=claimed_by,
        )
        session.add(task)
        await session.flush()
        if running_attempt:
            session.add(TaskAttempt(task_id=task.id, number=1, strategy_key="test"))
        await session.commit()
        task_id = task.id

    response = await client.delete(f"/api/tasks/{task_id}")
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "active task cannot be deleted; cancel it and wait for the worker to stop"
    )

    async with database.session() as session:
        assert await session.get(Task, task_id) is not None


async def test_missing_task_cannot_be_deleted(client: AsyncClient) -> None:
    response = await client.delete(f"/api/tasks/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["detail"] == "task not found"
