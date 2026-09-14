from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field

from autodev.db.models import Goal, Project
from autodev.domain.enums import PrivacyLevel, RiskLevel
from autodev.qa.discovery import CheckDiscovery


class PlannedTask(BaseModel):
    key: str
    title: str
    description: str
    task_type: str = "implementation"
    priority: int = Field(default=50, ge=0, le=100)
    risk: RiskLevel = RiskLevel.MEDIUM
    complexity: float = Field(default=0.5, ge=0, le=1)
    privacy_level: PrivacyLevel
    acceptance_criteria: list[str] = Field(default_factory=list)
    required_checks: list[list[str]] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class PlanOutput(BaseModel):
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    architecture: str
    milestones: list[str] = Field(default_factory=list)
    tasks: list[PlannedTask]
    deploy_requirements: list[str] = Field(default_factory=list)


class Planner(Protocol):
    async def plan(self, project: Project, goal: Goal) -> PlanOutput: ...


class BootstrapPlanner:
    """Conservative single-task planner used until an LLM-backed plan is configured."""

    async def plan(self, project: Project, goal: Goal) -> PlanOutput:
        repository = Path(project.repository_path)
        check_plan = await asyncio.to_thread(CheckDiscovery(repository).discover)
        return PlanOutput(
            assumptions=["The goal can be delivered as one initial scoped implementation task."],
            risks=["A later structured AI planning pass may split the task into a larger DAG."],
            architecture="Incremental change in the existing repository with deterministic checks.",
            milestones=["Implement and verify the requested goal"],
            tasks=[
                PlannedTask(
                    key="TASK-001",
                    title="Implement project goal",
                    description=goal.prompt,
                    privacy_level=project.privacy_level,
                    acceptance_criteria=[goal.prompt],
                    required_checks=check_plan.commands,
                )
            ],
            deploy_requirements=[],
        )
