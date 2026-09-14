from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select

from autodev.db.models import AuditEvent, Goal, Project, Task, TaskAttempt
from autodev.db.session import Database
from autodev.domain.enums import ProjectStatus, TaskStatus


async def test_create_project_and_goal_are_durable_and_audited(
    client: AsyncClient, database: Database
) -> None:
    project_response = await client.post(
        "/api/projects",
        json={
            "name": "fixture",
            "repository_path": "C:/projects/fixture",
            "privacy_level": "LOCAL_ONLY",
        },
    )
    assert project_response.status_code == 201
    project = project_response.json()
    assert project["status"] == "CREATED"
    assert project["privacy_level"] == "LOCAL_ONLY"

    goal_response = await client.post(
        f"/api/projects/{project['id']}/goals",
        json={"prompt": "Add tags to todo items with tests."},
    )
    assert goal_response.status_code == 201
    assert goal_response.json()["project_id"] == project["id"]

    list_response = await client.get("/api/projects")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [project["id"]]

    async with database.session() as session:
        audit_count = await session.scalar(select(func.count()).select_from(AuditEvent))
    assert audit_count == 2


async def test_create_goal_for_unknown_project_returns_404(client: AsyncClient) -> None:
    response = await client.post(
        "/api/projects/00000000-0000-0000-0000-000000000001/goals",
        json={"prompt": "Anything"},
    )
    assert response.status_code == 404


async def test_project_delete_removes_project_runtime_and_preserves_audit(
    client: AsyncClient, database: Database
) -> None:
    async with database.engine.begin() as connection:
        await connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    project_response = await client.post(
        "/api/projects",
        json={"name": "delete-project", "repository_path": "C:/delete-project"},
    )
    project_id = project_response.json()["id"]
    project_uuid = uuid.UUID(project_id)
    goal_response = await client.post(
        f"/api/projects/{project_id}/goals",
        json={"prompt": "Disposable goal"},
    )
    goal_id = goal_response.json()["id"]
    async with database.session() as session:
        task = Task(
            project_id=project_uuid,
            key="DELETE-WITH-PROJECT",
            title="Delete with project",
            status=TaskStatus.COMPLETED,
        )
        session.add(task)
        await session.flush()
        attempt = TaskAttempt(
            task_id=task.id,
            number=1,
            strategy_key="test",
            status=TaskStatus.COMPLETED.value,
        )
        session.add(attempt)
        await session.commit()
        task_id = task.id
        attempt_id = attempt.id

    response = await client.delete(f"/api/projects/{project_id}")
    assert response.status_code == 204
    assert response.content == b""

    async with database.session() as session:
        assert await session.get(Project, project_uuid) is None
        assert await session.get(Goal, uuid.UUID(goal_id)) is None
        assert await session.get(Task, task_id) is None
        assert await session.get(TaskAttempt, attempt_id) is None
        deletion_audit = await session.scalar(
            select(AuditEvent).where(AuditEvent.event == "project.deleted")
        )
        retained_events = list(
            await session.scalars(
                select(AuditEvent).where(
                    AuditEvent.event.in_(["project.created", "goal.created"])
                )
            )
        )
    assert deletion_audit is not None
    assert deletion_audit.project_id is None
    assert deletion_audit.details["project_id"] == project_id
    assert all(event.project_id is None for event in retained_events)


async def test_active_project_cannot_be_deleted(
    client: AsyncClient, database: Database
) -> None:
    async with database.session() as session:
        project = Project(
            name="active-project",
            repository_path="C:/active-project",
            status=ProjectStatus.IMPLEMENTING,
        )
        session.add(project)
        await session.commit()
        project_id = project.id

    response = await client.delete(f"/api/projects/{project_id}")
    assert response.status_code == 409
    assert response.json()["detail"] == (
        "active project cannot be deleted; pause it and wait for running tasks to stop"
    )

    async with database.session() as session:
        assert await session.get(Project, project_id) is not None


async def test_missing_project_cannot_be_deleted(client: AsyncClient) -> None:
    response = await client.delete("/api/projects/00000000-0000-0000-0000-000000000001")
    assert response.status_code == 404
    assert response.json()["detail"] == "project not found"


async def test_health_checks_database(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert response.headers["x-correlation-id"]


async def test_correlation_id_is_preserved(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"x-correlation-id": "request-fixture"})

    assert response.headers["x-correlation-id"] == "request-fixture"


async def test_readiness_reports_postgresql_as_durable_scheduler_source(
    client: AsyncClient,
) -> None:
    response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "database": "ok",
        "scheduler_source": "postgresql",
    }
