from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from autodev.domain.enums import PrivacyLevel, ProjectStatus, RiskLevel, TaskStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    repository_path: str = Field(min_length=1)
    privacy_level: PrivacyLevel = PrivacyLevel.PRIVATE


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    repository_path: str
    privacy_level: PrivacyLevel
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime


class GoalCreate(BaseModel):
    prompt: str = Field(min_length=1, max_length=100_000)


class GoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    prompt: str
    created_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    key: str
    title: str
    description: str
    task_type: str
    status: TaskStatus
    priority: int
    risk: RiskLevel
    complexity: float
    privacy_level: PrivacyLevel
    acceptance_criteria: list[str]
    required_checks: list[list[str]]
    attempt_count: int
    max_attempts: int
    created_at: datetime


class PlanRead(BaseModel):
    assumptions: list[str]
    risks: list[str]
    architecture: str
    milestones: list[str]
    tasks: list[TaskRead]
    deploy_requirements: list[str]


class TaskUpdate(BaseModel):
    priority: int | None = Field(default=None, ge=0, le=100)
    model_override: str | None = Field(default=None, min_length=1, max_length=300)
