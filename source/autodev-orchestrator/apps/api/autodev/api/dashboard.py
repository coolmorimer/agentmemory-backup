from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autodev.api.dependencies import get_session
from autodev.db.models import (
    AuditEvent,
    DeploymentRecord,
    ModelHealthRecord,
    ModelUsageRecord,
    Project,
    ProviderQuotaSnapshot,
    QaFindingRecord,
    Task,
)
from autodev.domain.enums import ProjectStatus, TaskStatus

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@router.get("/summary")
async def summary(session: SessionDependency) -> dict[str, Any]:
    project_rows = (
        await session.execute(select(Project.status, func.count()).group_by(Project.status))
    ).all()
    project_counts: dict[ProjectStatus, int] = {
        project_status: count for project_status, count in project_rows
    }
    task_rows = (
        await session.execute(select(Task.status, func.count()).group_by(Task.status))
    ).all()
    task_counts: dict[TaskStatus, int] = {task_status: count for task_status, count in task_rows}
    open_findings = await session.scalar(
        select(func.count()).select_from(QaFindingRecord).where(QaFindingRecord.status == "OPEN")
    )
    active_deployments = await session.scalar(
        select(func.count())
        .select_from(DeploymentRecord)
        .where(DeploymentRecord.status.in_(["PENDING", "DEPLOYING", "VERIFYING"]))
    )
    return {
        "projects": {key.value: value for key, value in project_counts.items()},
        "tasks": {key.value: value for key, value in task_counts.items()},
        "open_qa_findings": open_findings or 0,
        "active_deployments": active_deployments or 0,
    }


@router.get("/projects/{project_id}")
async def project_overview(project_id: uuid.UUID, session: SessionDependency) -> dict[str, Any]:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    tasks = list(
        await session.scalars(
            select(Task)
            .where(Task.project_id == project_id)
            .order_by(Task.priority.desc(), Task.key)
        )
    )
    events = list(
        await session.scalars(
            select(AuditEvent)
            .where(AuditEvent.project_id == project_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(100)
        )
    )
    deployments = list(
        await session.scalars(
            select(DeploymentRecord)
            .where(DeploymentRecord.project_id == project_id)
            .order_by(DeploymentRecord.started_at.desc())
        )
    )
    return {
        "project": {
            "id": str(project.id),
            "name": project.name,
            "status": project.status.value,
            "privacy_level": project.privacy_level.value,
        },
        "tasks": [
            {
                "id": str(task.id),
                "key": task.key,
                "title": task.title,
                "status": task.status.value,
                "attempts": task.attempt_count,
                "priority": task.priority,
            }
            for task in tasks
        ],
        "events": [
            {
                "event": event.event,
                "task_id": str(event.task_id) if event.task_id else None,
                "actor": event.actor,
                "created_at": event.created_at.isoformat(),
                "details": event.details,
            }
            for event in events
        ],
        "deployments": [
            {
                "id": str(deployment.id),
                "environment": deployment.environment,
                "release_ref": deployment.release_ref,
                "status": deployment.status,
            }
            for deployment in deployments
        ],
    }


@router.get("/models")
async def model_statistics(session: SessionDependency) -> list[dict[str, Any]]:
    success = case((ModelUsageRecord.status == "COMPLETED", 1.0), else_=0.0)
    rows = (
        await session.execute(
            select(
                ModelUsageRecord.provider,
                ModelUsageRecord.model,
                func.count(ModelUsageRecord.id),
                func.avg(success),
                func.avg(ModelUsageRecord.latency_seconds),
                func.sum(ModelUsageRecord.total_tokens),
            ).group_by(ModelUsageRecord.provider, ModelUsageRecord.model)
        )
    ).all()
    result: list[dict[str, Any]] = []
    for provider, model, calls, success_rate, latency, tokens in rows:
        health = await session.scalar(
            select(ModelHealthRecord).where(
                ModelHealthRecord.provider == provider,
                ModelHealthRecord.model == model,
            )
        )
        quota = await session.scalar(
            select(ProviderQuotaSnapshot)
            .where(
                ProviderQuotaSnapshot.provider == provider,
                ProviderQuotaSnapshot.model == model,
            )
            .order_by(ProviderQuotaSnapshot.updated_at.desc())
            .limit(1)
        )
        result.append(
            {
                "provider": provider,
                "model": model,
                "calls": calls,
                "success_rate": float(success_rate or 0),
                "average_latency_seconds": float(latency or 0),
                "tokens": tokens or 0,
                "health": health.state if health else "UNKNOWN",
                "requests_remaining": quota.requests_remaining if quota else None,
                "reset_at": quota.reset_at.isoformat() if quota and quota.reset_at else None,
            }
        )
    return result


@router.get("/metrics", response_class=Response)
async def metrics(session: SessionDependency) -> Response:
    total_tasks = await session.scalar(select(func.count()).select_from(Task)) or 0
    completed_tasks = (
        await session.scalar(
            select(func.count()).select_from(Task).where(Task.status == TaskStatus.COMPLETED)
        )
        or 0
    )
    incidents = (
        await session.scalar(
            select(func.count())
            .select_from(DeploymentRecord)
            .where(DeploymentRecord.status.in_(["ROLLED_BACK", "ROLLBACK_FAILED", "FAILED"]))
        )
        or 0
    )
    body = (
        "# TYPE autodev_tasks_total gauge\n"
        f"autodev_tasks_total {total_tasks}\n"
        "# TYPE autodev_tasks_completed gauge\n"
        f"autodev_tasks_completed {completed_tasks}\n"
        "# TYPE autodev_deployment_failures_total gauge\n"
        f"autodev_deployment_failures_total {incidents}\n"
    )
    return Response(content=body, media_type="text/plain; version=0.0.4")
