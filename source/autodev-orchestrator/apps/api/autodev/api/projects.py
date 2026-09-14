from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autodev.api.dependencies import get_session
from autodev.db.models import Project, Task, TaskAttempt
from autodev.domain.enums import ProjectStatus, TaskStatus
from autodev.domain.fsm import InvalidTransition
from autodev.events import Event
from autodev.orchestration.planner import BootstrapPlanner
from autodev.schemas.projects import (
    GoalCreate,
    GoalRead,
    PlanRead,
    ProjectCreate,
    ProjectRead,
    TaskRead,
)
from autodev.services.audit import record_audit
from autodev.services.projects import ProjectService
from autodev.services.tasks import InvalidPlan, PlanningService, list_project_tasks

router = APIRouter(prefix="/api/projects", tags=["projects"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]
service = ProjectService()
planning_service = PlanningService(BootstrapPlanner())
ACTIVE_PROJECT_STATUSES = frozenset(
    {
        ProjectStatus.RESEARCHING,
        ProjectStatus.PLANNING,
        ProjectStatus.IMPLEMENTING,
        ProjectStatus.TESTING,
        ProjectStatus.REVIEWING,
        ProjectStatus.STAGING,
        ProjectStatus.VERIFYING_STAGING,
        ProjectStatus.DEPLOYING,
        ProjectStatus.VERIFYING_PRODUCTION,
    }
)
ACTIVE_TASK_STATUSES = frozenset(
    {
        TaskStatus.RUNNING,
        TaskStatus.TESTING,
        TaskStatus.REVIEWING,
        TaskStatus.APPROVED,
    }
)


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, session: SessionDependency, request: Request
) -> ProjectRead:
    project = await service.create(
        session,
        name=payload.name,
        repository_path=payload.repository_path,
        privacy_level=payload.privacy_level,
    )
    await request.app.state.event_bus.publish(
        Event(name="project.created", project_id=project.id, payload={"name": project.name})
    )
    return ProjectRead.model_validate(project)


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: SessionDependency) -> list[ProjectRead]:
    projects = await service.list(session)
    return [ProjectRead.model_validate(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: uuid.UUID, session: SessionDependency) -> ProjectRead:
    project = await service.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    session: SessionDependency,
    request: Request,
) -> Response:
    project = await session.get(Project, project_id, with_for_update=True)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    tasks = list(
        await session.scalars(
            select(Task).where(Task.project_id == project.id).with_for_update()
        )
    )
    running_attempt_id = None
    if tasks:
        running_attempt_id = await session.scalar(
            select(TaskAttempt.id)
            .where(
                TaskAttempt.task_id.in_([task.id for task in tasks]),
                TaskAttempt.status == TaskStatus.RUNNING.value,
            )
            .limit(1)
        )
    active_task = next(
        (
            task
            for task in tasks
            if task.claimed_by or task.status in ACTIVE_TASK_STATUSES
        ),
        None,
    )
    if (
        project.status in ACTIVE_PROJECT_STATUSES
        or active_task is not None
        or running_attempt_id is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="active project cannot be deleted; pause it and wait for running tasks to stop",
        )

    deleted_details = {
        "project_id": str(project.id),
        "name": project.name,
        "status": project.status.value,
        "task_count": len(tasks),
    }
    await session.delete(project)
    await session.flush()
    record_audit(session, "project.deleted", details=deleted_details)
    await session.commit()
    await request.app.state.event_bus.publish(
        Event(name="project.deleted", project_id=project_id)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{project_id}/goals", response_model=GoalRead, status_code=status.HTTP_201_CREATED)
async def create_goal(
    project_id: uuid.UUID,
    payload: GoalCreate,
    session: SessionDependency,
    request: Request,
) -> GoalRead:
    project = await service.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    goal = await service.add_goal(session, project=project, prompt=payload.prompt)
    await request.app.state.event_bus.publish(
        Event(name="goal.created", project_id=project.id, payload={"goal_id": str(goal.id)})
    )
    return GoalRead.model_validate(goal)


@router.post("/{project_id}/plan", response_model=PlanRead)
async def plan_project(
    project_id: uuid.UUID, session: SessionDependency, request: Request
) -> PlanRead:
    project = await service.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    try:
        plan, tasks = await planning_service.create_plan(session, project=project)
    except (InvalidPlan, InvalidTransition) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    await request.app.state.event_bus.publish(
        Event(name="plan.created", project_id=project.id, payload={"tasks": len(tasks)})
    )
    for task in tasks:
        await request.app.state.event_bus.publish(
            Event(name="task.ready", project_id=project.id, task_id=task.id)
        )
    return PlanRead(
        assumptions=plan.assumptions,
        risks=plan.risks,
        architecture=plan.architecture,
        milestones=plan.milestones,
        tasks=[TaskRead.model_validate(task) for task in tasks],
        deploy_requirements=plan.deploy_requirements,
    )


@router.post("/{project_id}/start", response_model=ProjectRead)
async def start_project(
    project_id: uuid.UUID, session: SessionDependency, request: Request
) -> ProjectRead:
    project = await service.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    try:
        project = await planning_service.start(session, project=project)
    except InvalidTransition as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    await request.app.state.event_bus.publish(Event(name="project.started", project_id=project.id))
    return ProjectRead.model_validate(project)


@router.post("/{project_id}/pause", response_model=ProjectRead)
async def pause_project(
    project_id: uuid.UUID, session: SessionDependency, request: Request
) -> ProjectRead:
    project = await service.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    try:
        project = await service.pause(session, project=project)
    except InvalidTransition as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    await request.app.state.event_bus.publish(Event(name="project.paused", project_id=project.id))
    return ProjectRead.model_validate(project)


@router.post("/{project_id}/resume", response_model=ProjectRead)
async def resume_project(
    project_id: uuid.UUID, session: SessionDependency, request: Request
) -> ProjectRead:
    project = await service.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    try:
        project = await service.resume(session, project=project)
    except (InvalidTransition, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    await request.app.state.event_bus.publish(Event(name="project.resumed", project_id=project.id))
    return ProjectRead.model_validate(project)


@router.get("/{project_id}/tasks", response_model=list[TaskRead])
async def get_project_tasks(project_id: uuid.UUID, session: SessionDependency) -> list[TaskRead]:
    project = await service.get(session, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="project not found")
    tasks = await list_project_tasks(session, project_id)
    return [TaskRead.model_validate(task) for task in tasks]
