from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from autodev.db.models import Project, Task, TaskAttempt, TaskDependency
from autodev.domain.enums import ProjectStatus, TaskStatus
from autodev.domain.fsm import TaskStateMachine
from autodev.services.audit import record_audit


def utcnow() -> datetime:
    return datetime.now(UTC)


class Scheduler:
    """Durable task claiming; PostgreSQL turns the query into SKIP LOCKED row claims."""

    def __init__(self) -> None:
        self._fsm = TaskStateMachine()

    def claim_statement(self, *, now: datetime | None = None) -> Select[tuple[Task]]:
        current_time = now or utcnow()
        dependency = aliased(Task)
        unresolved_dependency = exists(
            select(TaskDependency.id)
            .join(dependency, dependency.id == TaskDependency.depends_on_task_id)
            .where(
                TaskDependency.task_id == Task.id,
                dependency.status != TaskStatus.COMPLETED,
            )
        )
        return (
            select(Task)
            .join(Project, Project.id == Task.project_id)
            .where(
                Project.status == ProjectStatus.IMPLEMENTING,
                Task.status == TaskStatus.READY,
                Task.next_run_at <= current_time,
                Task.attempt_count < Task.max_attempts,
                ~unresolved_dependency,
            )
            .order_by(Task.priority.desc(), Task.created_at.asc())
            .limit(1)
            .with_for_update(of=Task, skip_locked=True)
        )

    async def release_ready_dependencies(self, session: AsyncSession) -> int:
        """Promote waiting tasks whose complete dependency set has succeeded."""
        dependency = aliased(Task)
        unresolved_dependency = exists(
            select(TaskDependency.id)
            .join(dependency, dependency.id == TaskDependency.depends_on_task_id)
            .where(
                TaskDependency.task_id == Task.id,
                dependency.status != TaskStatus.COMPLETED,
            )
        )
        released = 0
        async with session.begin():
            tasks = list(
                await session.scalars(
                    select(Task)
                    .where(
                        Task.status == TaskStatus.WAITING_DEPENDENCY,
                        ~unresolved_dependency,
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            for task in tasks:
                task.status = self._fsm.transition(task.status, TaskStatus.READY)
                record_audit(
                    session,
                    "task.dependencies.resolved",
                    project_id=task.project_id,
                    task_id=task.id,
                )
                released += 1
        return released

    async def renew_lease(
        self,
        session: AsyncSession,
        *,
        task_id: uuid.UUID,
        worker_id: str,
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> bool:
        current_time = now or utcnow()
        async with session.begin():
            task = await session.get(Task, task_id, with_for_update=True)
            if (
                task is None
                or task.status is not TaskStatus.RUNNING
                or task.claimed_by != worker_id
            ):
                return False
            task.lease_expires_at = current_time + timedelta(seconds=lease_seconds)
        return True

    async def claim_next(
        self,
        session: AsyncSession,
        *,
        worker_id: str,
        strategy_key: str = "default",
        lease_seconds: int = 300,
        now: datetime | None = None,
    ) -> Task | None:
        current_time = now or utcnow()
        async with session.begin():
            task = await session.scalar(self.claim_statement(now=current_time))
            if task is None:
                return None

            task.status = self._fsm.transition(task.status, TaskStatus.RUNNING)
            task.attempt_count += 1
            task.claimed_by = worker_id
            task.lease_expires_at = current_time + timedelta(seconds=lease_seconds)
            session.add(
                TaskAttempt(
                    task_id=task.id,
                    number=task.attempt_count,
                    strategy_key=strategy_key,
                )
            )
            record_audit(
                session,
                "task.started",
                project_id=task.project_id,
                task_id=task.id,
                agent=worker_id,
                details={"attempt": task.attempt_count, "strategy": strategy_key},
            )
        return task

    async def recover_expired(
        self, session: AsyncSession, *, now: datetime | None = None
    ) -> tuple[int, int]:
        current_time = now or utcnow()
        recovered = 0
        failed = 0
        async with session.begin():
            tasks = list(
                await session.scalars(
                    select(Task)
                    .where(
                        Task.status == TaskStatus.RUNNING,
                        Task.lease_expires_at.is_not(None),
                        Task.lease_expires_at <= current_time,
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            for task in tasks:
                target = (
                    TaskStatus.FAILED
                    if task.attempt_count >= task.max_attempts
                    else TaskStatus.READY
                )
                task.status = self._fsm.transition(task.status, target)
                task.claimed_by = None
                task.lease_expires_at = None
                record_audit(
                    session,
                    "task.lease_expired",
                    project_id=task.project_id,
                    task_id=task.id,
                    details={"result": target.value},
                )
                if target is TaskStatus.FAILED:
                    failed += 1
                else:
                    recovered += 1
        return recovered, failed
