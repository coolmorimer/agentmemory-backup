from __future__ import annotations

import uuid
from pathlib import Path

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from autodev.db.models import (
    ApprovalRecord,
    DeploymentCheckRecord,
    DeploymentRecord,
    IncidentRecord,
    Project,
)
from autodev.db.session import Database
from autodev.deployment.base import (
    DeploymentRequest,
    DeploymentResult,
    DeploymentVerification,
    VerificationCheck,
)
from autodev.deployment.coordinator import DeploymentCoordinator
from autodev.deployment.docker_compose import (
    CommandResult,
    DockerComposeDeploymentAdapter,
)
from autodev.deployment.github_actions import GitHubActionsDeploymentAdapter
from autodev.deployment.policy import DeploymentEvidence, DeploymentPolicy


class FakeDeploymentAdapter:
    name = "fake"

    def __init__(self, *, verification_passes: bool) -> None:
        self.verification_passes = verification_passes
        self.calls: list[str] = []

    async def deploy(self, request: DeploymentRequest) -> DeploymentResult:
        self.calls.append("deploy")
        return DeploymentResult(
            external_id="deployment-1",
            release_ref=request.release_ref,
            previous_release_ref="release-previous",
        )

    async def verify(
        self, request: DeploymentRequest, deployment: DeploymentResult
    ) -> DeploymentVerification:
        self.calls.append("verify")
        return DeploymentVerification(
            checks=[
                VerificationCheck(
                    name="health",
                    passed=self.verification_passes,
                    detail="authorization: bearer secret-value"
                    if not self.verification_passes
                    else "ok",
                )
            ]
        )

    async def rollback(
        self, request: DeploymentRequest, deployment: DeploymentResult
    ) -> DeploymentResult:
        self.calls.append("rollback")
        return DeploymentResult(
            external_id="rollback-1",
            release_ref=deployment.previous_release_ref or "missing",
        )

    async def collect_logs(self, request: DeploymentRequest, deployment: DeploymentResult) -> str:
        self.calls.append("logs")
        return "password=secret-value service unhealthy"


async def create_project(database: Database) -> uuid.UUID:
    async with database.session() as session:
        project = Project(name="deploy", repository_path="C:/fixture")
        session.add(project)
        await session.commit()
        return project.id


def green_evidence() -> DeploymentEvidence:
    return DeploymentEvidence(
        ci_green=True,
        staging_green=True,
        smoke_green=True,
        healthcheck_defined=True,
        rollback_configured=True,
    )


async def test_production_requires_approval_before_adapter_call(
    database: Database, client: AsyncClient
) -> None:
    project_id = await create_project(database)
    adapter = FakeDeploymentAdapter(verification_passes=True)
    async with database.session() as session:
        outcome = await DeploymentCoordinator(adapter).run(
            session,
            project_id=project_id,
            environment="production",
            release_ref="release-1",
            evidence=green_evidence(),
        )
        await session.commit()

    assert outcome.status == "WAITING_APPROVAL"
    assert adapter.calls == []
    async with database.session() as session:
        approvals = await session.scalar(select(func.count()).select_from(ApprovalRecord))
    assert approvals == 1
    response = await client.post(
        f"/api/deployments/{outcome.deployment_id}/approval",
        json={"approved": True, "actor": "operator", "reason": "release window open"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
    assert (await client.get("/api/deployments")).json()[0]["id"] == str(outcome.deployment_id)
    assert (await client.get("/api/approvals")).json()[0]["status"] == "APPROVED"


async def test_generic_approval_reject_endpoint(database: Database, client: AsyncClient) -> None:
    project_id = await create_project(database)
    async with database.session() as session:
        approval = ApprovalRecord(project_id=project_id, action="dangerous.command")
        session.add(approval)
        await session.commit()
        approval_id = approval.id

    response = await client.post(
        f"/api/approvals/{approval_id}/reject",
        json={"actor": "operator", "reason": "maintenance freeze"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"


async def test_failed_verification_rolls_back_and_creates_redacted_incident(
    database: Database,
) -> None:
    project_id = await create_project(database)
    adapter = FakeDeploymentAdapter(verification_passes=False)
    async with database.session() as session:
        outcome = await DeploymentCoordinator(adapter).run(
            session,
            project_id=project_id,
            environment="production",
            release_ref="release-2",
            evidence=green_evidence(),
            approval_granted=True,
        )
        await session.commit()

    assert outcome.status == "ROLLED_BACK"
    assert outcome.rolled_back
    assert outcome.incident_id is not None
    assert adapter.calls == ["deploy", "verify", "logs", "rollback"]
    async with database.session() as session:
        deployment = await session.get(DeploymentRecord, outcome.deployment_id)
        incident = await session.get(IncidentRecord, outcome.incident_id)
        checks = await session.scalars(
            select(DeploymentCheckRecord).where(
                DeploymentCheckRecord.deployment_id == outcome.deployment_id
            )
        )
    assert deployment is not None and "secret-value" not in str(deployment.details)
    assert incident is not None and "secret-value" not in str(incident.details)
    assert [check.passed for check in checks] == [False]


async def test_auto_production_still_blocks_missing_safety_evidence(database: Database) -> None:
    project_id = await create_project(database)
    adapter = FakeDeploymentAdapter(verification_passes=True)
    async with database.session() as session:
        outcome = await DeploymentCoordinator(
            adapter, policy=DeploymentPolicy(production_mode="auto")
        ).run(
            session,
            project_id=project_id,
            environment="production",
            release_ref="release-3",
            evidence=DeploymentEvidence(ci_green=True),
        )
        await session.commit()

    assert outcome.status == "BLOCKED"
    assert "rollback is not configured" in outcome.blockers
    assert adapter.calls == []


class FakeExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, str]]] = []

    async def run(
        self, command: list[str], *, cwd: Path, environment: dict[str, str]
    ) -> CommandResult:
        self.calls.append((command, environment))
        output = "api" if "ps" in command else "ok"
        return CommandResult(exit_code=0, output=output)


async def test_docker_compose_adapter_uses_explicit_release_for_rollback(tmp_path: Path) -> None:
    executor = FakeExecutor()
    adapter = DockerComposeDeploymentAdapter(tmp_path, executor=executor)
    request = DeploymentRequest(
        project_id=uuid.uuid4(),
        environment="staging",
        release_ref="release-new",
        metadata={"previous_release_ref": "release-old"},
    )

    deployment = await adapter.deploy(request)
    verification = await adapter.verify(request, deployment)
    rollback = await adapter.rollback(request, deployment)

    assert verification.passed
    assert rollback.release_ref == "release-old"
    assert [call[1]["AUTODEV_RELEASE_REF"] for call in executor.calls] == [
        "release-new",
        "release-new",
        "release-old",
    ]


async def test_github_actions_adapter_uses_dispatch_run_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "fixture-token")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200,
                json={"workflow_run_id": 42, "html_url": "https://github.test/run/42"},
            )
        return httpx.Response(
            200,
            json={
                "id": 42,
                "status": "completed",
                "conclusion": "success",
                "html_url": "https://github.test/run/42",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = GitHubActionsDeploymentAdapter(
            "owner/repo", "deploy.yml", client=client, max_poll_attempts=1
        )
        request = DeploymentRequest(
            project_id=uuid.uuid4(), environment="staging", release_ref="main"
        )
        deployment = await adapter.deploy(request)
        verification = await adapter.verify(request, deployment)

    assert deployment.external_id == "42"
    assert verification.passed
