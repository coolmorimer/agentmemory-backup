from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    environment: str
    adapter: str
    release_ref: str
    previous_release_ref: str | None
    external_id: str | None
    status: str
    details: dict[str, object]
    started_at: datetime
    completed_at: datetime | None


class ApprovalDecision(BaseModel):
    approved: bool = True
    actor: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=4000)


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deployment_id: uuid.UUID | None
    action: str
    status: str
    decided_at: datetime | None
    decided_by: str | None
    reason: str | None
