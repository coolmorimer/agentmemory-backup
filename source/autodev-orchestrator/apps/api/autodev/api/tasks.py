from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autodev.api.dependencies import get_session
from autodev.db.models import AuditEvent, Task, TaskAttempt
from autodev.domain.enums import TaskStatus
from autodev.domain.fsm import InvalidTransition, TaskStateMachine
from autodev.events import Event
from autodev.schemas.projects import TaskRead, TaskUpdate
from autodev.services.audit import record_audit

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]
fsm = TaskStateMachine()
ACTIVE_TASK_STATUSES = frozenset(
    {
        TaskStatus.RUNNING,
        TaskStatus.TESTING,
        TaskStatus.REVIEWING,
        TaskStatus.APPROVED,
    }
)


async def _task_or_404(session: AsyncSession, task_id: uuid.UUID) -> Task:
    task = await session.get(Task, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="task not found")
    return task


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(task_id: uuid.UUID, session: SessionDependency) -> TaskRead:
    task = await _task_or_404(session, task_id)
    return TaskRead.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: uuid.UUID,
    session: SessionDependency,
    request: Request,
) -> Response:
    task = await _task_or_404(session, task_id)
    running_attempt_id = await session.scalar(
        select(TaskAttempt.id)
        .where(TaskAttempt.task_id == task.id, TaskAttempt.status == TaskStatus.RUNNING.value)
        .limit(1)
    )
    if task.claimed_by or task.status in ACTIVE_TASK_STATUSES or running_attempt_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="active task cannot be deleted; cancel it and wait for the worker to stop",
        )

    project_id = task.project_id
    deleted_details = {
        "task_id": str(task.id),
        "key": task.key,
        "title": task.title,
        "status": task.status.value,
    }
    await session.delete(task)
    await session.flush()
    record_audit(session, "task.deleted", project_id=project_id, details=deleted_details)
    await session.commit()
    await request.app.state.event_bus.publish(
        Event(name="task.deleted", project_id=project_id, task_id=task_id)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: uuid.UUID,
    payload: TaskUpdate,
    session: SessionDependency,
    request: Request,
) -> TaskRead:
    task = await _task_or_404(session, task_id)
    if payload.priority is not None:
        task.priority = payload.priority
    if payload.model_override is not None:
        task.context_requirements = {
            **task.context_requirements,
            "model_override": payload.model_override,
        }
    record_audit(
        session,
        "task.updated",
        project_id=task.project_id,
        task_id=task.id,
        details=payload.model_dump(exclude_none=True),
    )
    await session.commit()
    await session.refresh(task)
    await request.app.state.event_bus.publish(
        Event(name="task.updated", project_id=task.project_id, task_id=task.id)
    )
    return TaskRead.model_validate(task)


@router.post("/{task_id}/retry", response_model=TaskRead)
async def retry_task(task_id: uuid.UUID, session: SessionDependency, request: Request) -> TaskRead:
    task = await _task_or_404(session, task_id)
    try:
        task.status = fsm.transition(task.status, TaskStatus.READY)
    except InvalidTransition as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if task.attempt_count >= task.max_attempts:
        task.max_attempts = task.attempt_count + 1
    task.claimed_by = None
    task.lease_expires_at = None
    task.next_run_at = datetime.now(UTC)
    record_audit(session, "task.retried", project_id=task.project_id, task_id=task.id)
    await session.commit()
    await session.refresh(task)
    await request.app.state.event_bus.publish(
        Event(name="task.ready", project_id=task.project_id, task_id=task.id)
    )
    return TaskRead.model_validate(task)


@router.post("/{task_id}/pause", response_model=TaskRead)
async def pause_task(task_id: uuid.UUID, session: SessionDependency, request: Request) -> TaskRead:
    task = await _task_or_404(session, task_id)
    previous_status = task.status
    try:
        task.status = fsm.transition(task.status, TaskStatus.PAUSED)
    except InvalidTransition as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    resume_status = (
        previous_status
        if previous_status in {TaskStatus.DRAFT, TaskStatus.WAITING_DEPENDENCY}
        else TaskStatus.READY
    )
    if task.claimed_by is None:
        task.lease_expires_at = None
    record_audit(
        session,
        "task.paused",
        project_id=task.project_id,
        task_id=task.id,
        details={
            "previous_status": previous_status.value,
            "resume_status": resume_status.value,
        },
    )
    await session.commit()
    await session.refresh(task)
    await request.app.state.event_bus.publish(
        Event(name="task.paused", project_id=task.project_id, task_id=task.id)
    )
    return TaskRead.model_validate(task)


@router.post("/{task_id}/resume", response_model=TaskRead)
async def resume_task(task_id: uuid.UUID, session: SessionDependency, request: Request) -> TaskRead:
    task = await _task_or_404(session, task_id)
    if task.status is not TaskStatus.PAUSED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="task is not paused")
    running_attempt_id = await session.scalar(
        select(TaskAttempt.id)
        .where(TaskAttempt.task_id == task.id, TaskAttempt.status == TaskStatus.RUNNING.value)
        .limit(1)
    )
    if task.claimed_by or running_attempt_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="task is still stopping; wait for the worker before resuming it",
        )
    paused_event = await session.scalar(
        select(AuditEvent)
        .where(AuditEvent.task_id == task.id, AuditEvent.event == "task.paused")
        .order_by(AuditEvent.created_at.desc())
        .limit(1)
    )
    if paused_event is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="task has no pause checkpoint",
        )
    raw_resume_status = paused_event.details.get("resume_status")
    if not isinstance(raw_resume_status, str):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="task pause checkpoint is invalid",
        )
    try:
        target = TaskStatus(raw_resume_status)
        task.status = fsm.transition(task.status, target)
    except (InvalidTransition, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="task pause checkpoint is invalid",
        ) from error
    task.claimed_by = None
    task.lease_expires_at = None
    if target is TaskStatus.READY:
        task.next_run_at = datetime.now(UTC)
    record_audit(
        session,
        "task.resumed",
        project_id=task.project_id,
        task_id=task.id,
        details={"restored_status": target.value},
    )
    await session.commit()
    await session.refresh(task)
    await request.app.state.event_bus.publish(
        Event(
            name="task.ready" if target is TaskStatus.READY else "task.resumed",
            project_id=task.project_id,
            task_id=task.id,
        )
    )
    return TaskRead.model_validate(task)


@router.post("/{task_id}/cancel", response_model=TaskRead)
async def cancel_task(task_id: uuid.UUID, session: SessionDependency, request: Request) -> TaskRead:
    task = await _task_or_404(session, task_id)
    try:
        task.status = fsm.transition(task.status, TaskStatus.CANCELLED)
    except InvalidTransition as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    task.claimed_by = None
    task.lease_expires_at = None
    record_audit(session, "task.cancelled", project_id=task.project_id, task_id=task.id)
    await session.commit()
    await session.refresh(task)
    await request.app.state.event_bus.publish(
        Event(name="task.cancelled", project_id=task.project_id, task_id=task.id)
    )
    return TaskRead.model_validate(task)
