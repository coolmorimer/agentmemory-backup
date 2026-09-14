from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from autodev.db.models import (
    ApprovalRecord,
    DeploymentCheckRecord,
    DeploymentRecord,
    IncidentRecord,
)
from autodev.deployment.base import DeploymentAdapter, DeploymentError, DeploymentRequest
from autodev.deployment.policy import DeploymentEvidence, DeploymentPolicy
from autodev.security.redaction import Redactor
from autodev.services.audit import record_audit


class DeploymentOutcome(BaseModel):
    deployment_id: uuid.UUID
    status: str
    checks_passed: bool = False
    rolled_back: bool = False
    blockers: list[str] = Field(default_factory=list)
    incident_id: uuid.UUID | None = None


class DeploymentCoordinator:
    def __init__(
        self,
        adapter: DeploymentAdapter,
        *,
        policy: DeploymentPolicy | None = None,
        redactor: Redactor | None = None,
    ) -> None:
        self.adapter = adapter
        self.policy = policy or DeploymentPolicy()
        self.redactor = redactor or Redactor()

    async def run(
        self,
        session: AsyncSession,
        *,
        project_id: uuid.UUID,
        environment: Literal["staging", "production"],
        release_ref: str,
        evidence: DeploymentEvidence,
        approval_granted: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> DeploymentOutcome:
        decision = self.policy.evaluate(environment, evidence, approval_granted=approval_granted)
        deployment = DeploymentRecord(
            project_id=project_id,
            environment=environment,
            adapter=self.adapter.name,
            release_ref=release_ref,
            status="PENDING",
            details={},
        )
        session.add(deployment)
        await session.flush()
        if decision.blockers:
            deployment.status = "BLOCKED"
            deployment.details = {"blockers": decision.blockers}
            deployment.completed_at = datetime.now(UTC)
            record_audit(
                session,
                "deployment.blocked",
                project_id=project_id,
                details={"deployment_id": str(deployment.id), "blockers": decision.blockers},
            )
            return DeploymentOutcome(
                deployment_id=deployment.id,
                status=deployment.status,
                blockers=decision.blockers,
            )
        if decision.requires_approval:
            deployment.status = "WAITING_APPROVAL"
            session.add(
                ApprovalRecord(
                    project_id=project_id,
                    deployment_id=deployment.id,
                    action="production.deploy",
                    status="PENDING",
                )
            )
            record_audit(
                session,
                "deployment.approval.requested",
                project_id=project_id,
                details={"deployment_id": str(deployment.id)},
            )
            return DeploymentOutcome(deployment_id=deployment.id, status=deployment.status)

        request = DeploymentRequest(
            project_id=project_id,
            environment=environment,
            release_ref=release_ref,
            metadata=metadata or {},
        )
        deployment.status = "DEPLOYING"
        try:
            result = await self.adapter.deploy(request)
            deployment.external_id = result.external_id
            deployment.previous_release_ref = result.previous_release_ref
            deployment.status = "VERIFYING"
            verification = await self.adapter.verify(request, result)
        except DeploymentError as error:
            deployment.status = "FAILED"
            deployment.details = {"error": self.redactor.text(str(error))[-4000:]}
            deployment.completed_at = datetime.now(UTC)
            incident = self._incident(
                session,
                project_id=project_id,
                deployment_id=deployment.id,
                summary="Deployment adapter failed before verification",
                details=deployment.details,
            )
            return DeploymentOutcome(
                deployment_id=deployment.id,
                status=deployment.status,
                incident_id=incident.id,
            )

        for check in verification.checks:
            session.add(
                DeploymentCheckRecord(
                    deployment_id=deployment.id,
                    name=check.name,
                    passed=check.passed,
                    detail=self.redactor.text(check.detail)[-16_000:],
                    artifact_path=check.artifact_path,
                )
            )
        if verification.passed:
            deployment.status = "COMPLETED"
            deployment.completed_at = datetime.now(UTC)
            record_audit(
                session,
                "deployment.completed",
                project_id=project_id,
                details={"deployment_id": str(deployment.id), "environment": environment},
            )
            return DeploymentOutcome(
                deployment_id=deployment.id,
                status=deployment.status,
                checks_passed=True,
            )

        logs = ""
        try:
            logs = self.redactor.text(await self.adapter.collect_logs(request, result))[-16_000:]
            await self.adapter.rollback(request, result)
            deployment.status = "ROLLED_BACK"
            rolled_back = True
        except DeploymentError as error:
            logs = f"{logs}\nrollback error: {self.redactor.text(str(error))}"[-16_000:]
            deployment.status = "ROLLBACK_FAILED"
            rolled_back = False
        deployment.completed_at = datetime.now(UTC)
        deployment.details = {"logs": logs}
        incident = self._incident(
            session,
            project_id=project_id,
            deployment_id=deployment.id,
            summary="Deployment verification failed",
            details={"rolled_back": rolled_back, "logs": logs},
        )
        record_audit(
            session,
            "deployment.rollback.completed" if rolled_back else "deployment.rollback.failed",
            project_id=project_id,
            details={"deployment_id": str(deployment.id)},
        )
        return DeploymentOutcome(
            deployment_id=deployment.id,
            status=deployment.status,
            rolled_back=rolled_back,
            incident_id=incident.id,
        )

    @staticmethod
    def _incident(
        session: AsyncSession,
        *,
        project_id: uuid.UUID,
        deployment_id: uuid.UUID,
        summary: str,
        details: dict[str, object],
    ) -> IncidentRecord:
        incident = IncidentRecord(
            id=uuid.uuid4(),
            project_id=project_id,
            deployment_id=deployment_id,
            severity="CRITICAL",
            status="OPEN",
            summary=summary,
            details=details,
        )
        session.add(incident)
        return incident
