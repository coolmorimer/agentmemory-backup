from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autodev.api.dependencies import get_session
from autodev.db.models import ApprovalRecord, DeploymentRecord
from autodev.events import Event
from autodev.schemas.deployments import ApprovalDecision, ApprovalRead, DeploymentRead
from autodev.services.audit import record_audit

router = APIRouter(prefix="/api/deployments", tags=["deployments"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[DeploymentRead])
async def list_deployments(session: SessionDependency) -> list[DeploymentRead]:
    deployments = list(
        await session.scalars(
            select(DeploymentRecord).order_by(DeploymentRecord.started_at.desc()).limit(200)
        )
    )
    return [DeploymentRead.model_validate(deployment) for deployment in deployments]


@router.get("/{deployment_id}", response_model=DeploymentRead)
async def get_deployment(deployment_id: uuid.UUID, session: SessionDependency) -> DeploymentRead:
    deployment = await session.get(DeploymentRecord, deployment_id)
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deployment not found")
    return DeploymentRead.model_validate(deployment)


@router.post("/{deployment_id}/approval", response_model=ApprovalRead)
async def decide_deployment(
    deployment_id: uuid.UUID,
    payload: ApprovalDecision,
    session: SessionDependency,
    request: Request,
) -> ApprovalRead:
    deployment = await session.get(DeploymentRecord, deployment_id, with_for_update=True)
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="deployment not found")
    approval = await session.scalar(
        select(ApprovalRecord).where(
            ApprovalRecord.deployment_id == deployment_id,
            ApprovalRecord.status == "PENDING",
        )
    )
    if approval is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="deployment has no pending approval",
        )
    approval.status = "APPROVED" if payload.approved else "REJECTED"
    approval.decided_at = datetime.now(UTC)
    approval.decided_by = payload.actor
    approval.reason = payload.reason
    deployment.status = approval.status
    record_audit(
        session,
        "deployment.approval.decided",
        project_id=deployment.project_id,
        actor=payload.actor,
        details={
            "deployment_id": str(deployment.id),
            "decision": approval.status,
        },
    )
    await session.commit()
    await session.refresh(approval)
    await request.app.state.event_bus.publish(
        Event(
            name="deployment.approval.decided",
            project_id=deployment.project_id,
            payload={"deployment_id": str(deployment.id), "decision": approval.status},
        )
    )
    return ApprovalRead.model_validate(approval)
