from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autodev.db.models import AuditEvent, Goal, Project
from autodev.domain.enums import PrivacyLevel, ProjectStatus
from autodev.domain.fsm import ProjectStateMachine
from autodev.services.audit import record_audit


class ProjectService:
    def __init__(self) -> None:
        self._fsm = ProjectStateMachine()

    async def create(
        self,
        session: AsyncSession,
        *,
        name: str,
        repository_path: str,
        privacy_level: PrivacyLevel,
    ) -> Project:
        project = Project(name=name, repository_path=repository_path, privacy_level=privacy_level)
        session.add(project)
        await session.flush()
        record_audit(
            session,
            "project.created",
            project_id=project.id,
            details={"name": project.name, "privacy_level": project.privacy_level.value},
        )
        await session.commit()
        await session.refresh(project)
        return project

    async def list(self, session: AsyncSession) -> list[Project]:
        result = await session.scalars(select(Project).order_by(Project.created_at.desc()))
        return list(result)

    async def get(self, session: AsyncSession, project_id: uuid.UUID) -> Project | None:
        return await session.get(Project, project_id)

    async def add_goal(self, session: AsyncSession, *, project: Project, prompt: str) -> Goal:
        goal = Goal(project_id=project.id, prompt=prompt)
        session.add(goal)
        await session.flush()
        record_audit(
            session,
            "goal.created",
            project_id=project.id,
            details={"goal_id": str(goal.id)},
        )
        await session.commit()
        await session.refresh(goal)
        return goal

    async def pause(self, session: AsyncSession, *, project: Project) -> Project:
        previous_status = project.status
        project.status = self._fsm.transition(project.status, ProjectStatus.PAUSED)
        record_audit(
            session,
            "project.paused",
            project_id=project.id,
            details={"previous_status": previous_status.value},
        )
        await session.commit()
        await session.refresh(project)
        return project

    async def resume(self, session: AsyncSession, *, project: Project) -> Project:
        paused_event = await session.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.project_id == project.id,
                AuditEvent.event == "project.paused",
            )
            .order_by(AuditEvent.created_at.desc())
            .limit(1)
        )
        if paused_event is None:
            raise ValueError("project has no pause checkpoint")
        previous = paused_event.details.get("previous_status")
        if not isinstance(previous, str):
            raise ValueError("project pause checkpoint is invalid")
        target = ProjectStatus(previous)
        project.status = self._fsm.transition(project.status, target)
        record_audit(
            session,
            "project.resumed",
            project_id=project.id,
            details={"restored_status": target.value},
        )
        await session.commit()
        await session.refresh(project)
        return project
