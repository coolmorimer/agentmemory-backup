from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import delete, text

from autodev.db.models import Project, Task
from autodev.db.session import Database
from autodev.domain.enums import ProjectStatus, TaskStatus
from autodev.orchestration.scheduler import Scheduler

DATABASE_URL = os.getenv("AUTODEV_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="AUTODEV_TEST_DATABASE_URL is required for PostgreSQL tests"
)


async def test_postgresql_concurrent_workers_claim_distinct_tasks() -> None:
    assert DATABASE_URL is not None
    database = Database(DATABASE_URL)
    project_id = None
    try:
        async with database.session() as session:
            project = Project(
                name="postgres-claim-test",
                repository_path="C:/fixture",
                status=ProjectStatus.IMPLEMENTING,
            )
            session.add(project)
            await session.flush()
            project_id = project.id
            session.add_all(
                [
                    Task(
                        project_id=project.id,
                        key="PG-1",
                        title="First",
                        status=TaskStatus.READY,
                        priority=50,
                    ),
                    Task(
                        project_id=project.id,
                        key="PG-2",
                        title="Second",
                        status=TaskStatus.READY,
                        priority=50,
                    ),
                ]
            )
            await session.commit()

        async def claim(worker_id: str) -> Task | None:
            async with database.session() as session:
                return await Scheduler().claim_next(session, worker_id=worker_id)

        first, second = await asyncio.gather(claim("worker-1"), claim("worker-2"))

        assert first is not None
        assert second is not None
        assert first.id != second.id
        assert {first.claimed_by, second.claimed_by} == {"worker-1", "worker-2"}

        async with database.session() as session:
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
        assert revision == "20260903_0007"
    finally:
        if project_id is not None:
            async with database.session() as session:
                await session.execute(delete(Project).where(Project.id == project_id))
                await session.commit()
        await database.dispose()
