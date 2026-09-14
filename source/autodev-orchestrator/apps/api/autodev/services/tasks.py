from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autodev.db.models import Goal, Project, Task, TaskDependency
from autodev.domain.enums import ProjectStatus, TaskStatus
from autodev.domain.fsm import ProjectStateMachine
from autodev.orchestration.planner import Planner, PlanOutput
from autodev.services.audit import record_audit


class InvalidPlan(ValueError):
    pass


class PlanningService:
    def __init__(self, planner: Planner) -> None:
        self._planner = planner
        self._project_fsm = ProjectStateMachine()

    async def create_plan(
        self, session: AsyncSession, *, project: Project
    ) -> tuple[PlanOutput, list[Task]]:
        goal = await session.scalar(
            select(Goal)
            .where(Goal.project_id == project.id)
            .order_by(Goal.created_at.desc())
            .limit(1)
        )
        if goal is None:
            raise InvalidPlan("project has no goal")
        plan = await self._planner.plan(project, goal)
        self._validate_plan(plan)

        project.status = self._project_fsm.transition(project.status, ProjectStatus.PLANNING)
        task_by_key: dict[str, Task] = {}
        for planned in plan.tasks:
            status = TaskStatus.WAITING_DEPENDENCY if planned.depends_on else TaskStatus.READY
            task = Task(
                project_id=project.id,
                key=planned.key,
                title=planned.title,
                description=planned.description,
                task_type=planned.task_type,
                status=status,
                priority=planned.priority,
                risk=planned.risk,
                complexity=planned.complexity,
                privacy_level=planned.privacy_level,
                acceptance_criteria=planned.acceptance_criteria,
                required_checks=planned.required_checks,
            )
            session.add(task)
            task_by_key[planned.key] = task
        await session.flush()
        for planned in plan.tasks:
            task = task_by_key[planned.key]
            for dependency_key in planned.depends_on:
                session.add(
                    TaskDependency(
                        task_id=task.id,
                        depends_on_task_id=task_by_key[dependency_key].id,
                    )
                )
        project.status = self._project_fsm.transition(project.status, ProjectStatus.READY)
        record_audit(
            session,
            "plan.created",
            project_id=project.id,
            details={"task_count": len(plan.tasks), "architecture": plan.architecture},
        )
        await session.commit()
        return plan, list(task_by_key.values())

    async def start(self, session: AsyncSession, *, project: Project) -> Project:
        project.status = self._project_fsm.transition(project.status, ProjectStatus.IMPLEMENTING)
        record_audit(session, "project.started", project_id=project.id)
        await session.commit()
        await session.refresh(project)
        return project

    @staticmethod
    def _validate_plan(plan: PlanOutput) -> None:
        if not plan.tasks:
            raise InvalidPlan("plan must include at least one task")
        keys = [task.key for task in plan.tasks]
        if len(keys) != len(set(keys)):
            raise InvalidPlan("task keys must be unique")
        key_set = set(keys)
        for task in plan.tasks:
            if task.key in task.depends_on:
                raise InvalidPlan(f"task {task.key} cannot depend on itself")
            unknown = set(task.depends_on) - key_set
            if unknown:
                raise InvalidPlan(f"task {task.key} has unknown dependencies: {sorted(unknown)}")

        graph = {task.key: set(task.depends_on) for task in plan.tasks}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(key: str) -> None:
            if key in visiting:
                raise InvalidPlan("task dependency graph contains a cycle")
            if key in visited:
                return
            visiting.add(key)
            for dependency in graph[key]:
                visit(dependency)
            visiting.remove(key)
            visited.add(key)

        for key in keys:
            visit(key)


async def list_project_tasks(session: AsyncSession, project_id: uuid.UUID) -> list[Task]:
    tasks = await session.scalars(
        select(Task).where(Task.project_id == project_id).order_by(Task.created_at, Task.key)
    )
    return list(tasks)
