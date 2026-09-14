from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from autodev.db.models import AuditEvent, Project, Task, TaskAttempt, TaskDependency
from autodev.db.session import Database
from autodev.domain.enums import ProjectStatus, TaskStatus
from autodev.orchestration.scheduler import Scheduler


async def test_claim_prefers_ready_high_priority_task_and_records_attempt(
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
        session.add_all(
            [
                Task(
                    project_id=project.id,
                    key="LOW",
                    title="Low",
                    status=TaskStatus.READY,
                    priority=1,
                ),
                Task(
                    project_id=project.id,
                    key="HIGH",
                    title="High",
                    status=TaskStatus.READY,
                    priority=99,
                ),
            ]
        )
        await session.commit()

    async with database.session() as session:
        claimed = await Scheduler().claim_next(session, worker_id="worker-1")
        assert claimed is not None
        assert claimed.key == "HIGH"
        assert claimed.status is TaskStatus.RUNNING
        assert claimed.attempt_count == 1

    async with database.session() as session:
        attempts = await session.scalar(select(func.count()).select_from(TaskAttempt))
        events = await session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.event == "task.started")
        )
    assert attempts == 1
    assert events == 1


async def test_claim_skips_task_with_unresolved_dependency(database: Database) -> None:
    async with database.session() as session:
        project = Project(
            name="fixture",
            repository_path="C:/fixture",
            status=ProjectStatus.IMPLEMENTING,
        )
        session.add(project)
        await session.flush()
        prerequisite = Task(
            project_id=project.id, key="FIRST", title="First", status=TaskStatus.READY, priority=1
        )
        dependent = Task(
            project_id=project.id,
            key="SECOND",
            title="Second",
            status=TaskStatus.READY,
            priority=99,
        )
        session.add_all([prerequisite, dependent])
        await session.flush()
        session.add(TaskDependency(task_id=dependent.id, depends_on_task_id=prerequisite.id))
        await session.commit()

    async with database.session() as session:
        claimed = await Scheduler().claim_next(session, worker_id="worker-1")
    assert claimed is not None
    assert claimed.key == "FIRST"


async def test_claim_skips_ready_task_when_project_is_paused(database: Database) -> None:
    async with database.session() as session:
        project = Project(
            name="paused-fixture",
            repository_path="C:/fixture",
            status=ProjectStatus.PAUSED,
        )
        session.add(project)
        await session.flush()
        session.add(
            Task(
                project_id=project.id,
                key="PAUSED",
                title="Must wait",
                status=TaskStatus.READY,
            )
        )
        await session.commit()

    async with database.session() as session:
        assert await Scheduler().claim_next(session, worker_id="worker-1") is None


async def test_completed_dependencies_release_waiting_task(database: Database) -> None:
    async with database.session() as session:
        project = Project(name="fixture", repository_path="C:/fixture")
        session.add(project)
        await session.flush()
        prerequisite = Task(
            project_id=project.id,
            key="FIRST",
            title="First",
            status=TaskStatus.COMPLETED,
        )
        dependent = Task(
            project_id=project.id,
            key="SECOND",
            title="Second",
            status=TaskStatus.WAITING_DEPENDENCY,
        )
        session.add_all([prerequisite, dependent])
        await session.flush()
        dependent_id = dependent.id
        session.add(TaskDependency(task_id=dependent.id, depends_on_task_id=prerequisite.id))
        await session.commit()

    async with database.session() as session:
        assert await Scheduler().release_ready_dependencies(session) == 1

    async with database.session() as session:
        released = await session.get(Task, dependent_id)
        assert released is not None
        assert released.status is TaskStatus.READY
        events = await session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event == "task.dependencies.resolved")
        )
    assert events == 1


async def test_recover_expired_lease_requeues_or_fails_at_attempt_limit(
    database: Database,
) -> None:
    now = datetime.now(UTC)
    async with database.session() as session:
        project = Project(name="fixture", repository_path="C:/fixture")
        session.add(project)
        await session.flush()
        session.add_all(
            [
                Task(
                    project_id=project.id,
                    key="RETRY",
                    title="Retry",
                    status=TaskStatus.RUNNING,
                    attempt_count=1,
                    max_attempts=3,
                    claimed_by="dead-worker",
                    lease_expires_at=now - timedelta(seconds=1),
                ),
                Task(
                    project_id=project.id,
                    key="EXHAUSTED",
                    title="Exhausted",
                    status=TaskStatus.RUNNING,
                    attempt_count=3,
                    max_attempts=3,
                    claimed_by="dead-worker",
                    lease_expires_at=now - timedelta(seconds=1),
                ),
            ]
        )
        await session.commit()

    async with database.session() as session:
        assert await Scheduler().recover_expired(session, now=now) == (1, 1)

    async with database.session() as session:
        result = await session.execute(select(Task.key, Task.status))
        statuses = dict(result.all())
    assert statuses == {"RETRY": TaskStatus.READY, "EXHAUSTED": TaskStatus.FAILED}


def test_postgresql_claim_uses_skip_locked() -> None:
    sql = str(Scheduler().claim_statement().compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE OF tasks SKIP LOCKED" in sql
    assert "projects.status" in sql
