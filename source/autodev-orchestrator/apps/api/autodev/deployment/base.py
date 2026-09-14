from __future__ import annotations

import uuid
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field


class DeploymentError(RuntimeError):
    pass


class DeploymentRequest(BaseModel):
    project_id: uuid.UUID
    environment: Literal["staging", "production"]
    release_ref: str = Field(min_length=1, max_length=300)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeploymentResult(BaseModel):
    external_id: str
    release_ref: str
    previous_release_ref: str | None = None
    detail: str = ""


class VerificationCheck(BaseModel):
    name: str
    passed: bool
    detail: str = ""
    artifact_path: str | None = None


class DeploymentVerification(BaseModel):
    checks: list[VerificationCheck]

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)


class DeploymentAdapter(Protocol):
    name: str

    async def deploy(self, request: DeploymentRequest) -> DeploymentResult: ...

    async def verify(
        self, request: DeploymentRequest, deployment: DeploymentResult
    ) -> DeploymentVerification: ...

    async def rollback(
        self, request: DeploymentRequest, deployment: DeploymentResult
    ) -> DeploymentResult: ...

    async def collect_logs(
        self, request: DeploymentRequest, deployment: DeploymentResult
    ) -> str: ...
