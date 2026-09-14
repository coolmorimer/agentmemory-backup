from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from autodev.db.models import AuditEvent, Project, Task
from autodev.db.session import Database
from autodev.domain.enums import ProjectStatus, TaskStatus
from autodev.orchestration.worker import WorkerPool


class ConcurrentExecutor:
    def __init__(self) -> None:
        self.active = 0
        self.maximum_active = 0
        self.completed: list[uuid.UUID] = []

    async def execute_claimed(self, task_id: uuid.UUID) -> object:
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        await asyncio.sleep(0.01)
        self.completed.append(task_id)
        self.active -= 1
        return object()


class CrashingExecutor:
    async def execute_claimed(self, task_id: uuid.UUID) -> object:
        raise RuntimeError(f"boom {task_id}")


async def test_worker_pool_runs_claimed_tasks_concurrently(database: Database) -> None:
    async with database.session() as session:
        project = Project(
            name="fixture",
            repository_path="C:/fixture",
            status=ProjectStatus.IMPLEMENTING,
        )
        session.add(project)
        await session.flush()
        session.add_all(
            [
                Task(
                    project_id=project.id,
                    key=f"TASK-{number}",
                    title=f"Task {number}",
                    status=TaskStatus.READY,
                )
                for number in range(3)
            ]
        )
        await session.commit()

    executor = ConcurrentExecutor()
    pool = WorkerPool(database, executor, concurrency=3, heartbeat_interval=10)

    assert await pool.run_once() == 3
    assert executor.maximum_active == 3
    assert len(executor.completed) == 3


async def test_worker_pool_requeues_task_after_unexpected_executor_crash(
    database: Database,
) -> None:
    async with database.session() as session:
        project = Project(
            name="fixture",
            repository_path="C:/fixture",
            status=ProjectStatus.IMPLEMENTING,
        )
        session.add(project)
        await session.flush()
        task = Task(
            project_id=project.id,
            key="CRASH",
            title="Crash",
            status=TaskStatus.READY,
        )
        session.add(task)
        await session.commit()
        task_id = task.id

    pool = WorkerPool(database, CrashingExecutor(), concurrency=1, heartbeat_interval=10)
    assert await pool.run_once() == 1

    async with database.session() as session:
        task = await session.get(Task, task_id)
        event = await session.scalar(
            select(AuditEvent).where(AuditEvent.event == "task.worker.crashed")
        )
    assert task is not None
    assert task.status is TaskStatus.READY
    assert task.claimed_by is None
    assert event is not None
    assert event.details["error_type"] == "RuntimeError"
