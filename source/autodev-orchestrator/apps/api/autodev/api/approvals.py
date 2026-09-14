from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autodev.api.dependencies import get_session
from autodev.db.models import ApprovalRecord
from autodev.events import Event
from autodev.schemas.deployments import ApprovalDecision, ApprovalRead
from autodev.services.audit import record_audit

router = APIRouter(prefix="/api/approvals", tags=["approvals"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@router.get("", response_model=list[ApprovalRead])
async def list_approvals(session: SessionDependency) -> list[ApprovalRead]:
    approvals = list(
        await session.scalars(
            select(ApprovalRecord).order_by(ApprovalRecord.requested_at.desc()).limit(200)
        )
    )
    return [ApprovalRead.model_validate(approval) for approval in approvals]


async def _decide(
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    session: AsyncSession,
    request: Request,
    *,
    approved: bool,
) -> ApprovalRead:
    approval = await session.get(ApprovalRecord, approval_id, with_for_update=True)
    if approval is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval not found")
    if approval.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="approval is not pending")
    approval.status = "APPROVED" if approved else "REJECTED"
    approval.decided_at = datetime.now(UTC)
    approval.decided_by = payload.actor
    approval.reason = payload.reason
    record_audit(
        session,
        "approval.decided",
        project_id=approval.project_id,
        actor=payload.actor,
        details={"approval_id": str(approval.id), "decision": approval.status},
    )
    await session.commit()
    await session.refresh(approval)
    await request.app.state.event_bus.publish(
        Event(
            name="approval.decided",
            project_id=approval.project_id,
            payload={"approval_id": str(approval.id), "decision": approval.status},
        )
    )
    return ApprovalRead.model_validate(approval)


@router.post("/{approval_id}/approve", response_model=ApprovalRead)
async def approve(
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    session: SessionDependency,
    request: Request,
) -> ApprovalRead:
    return await _decide(approval_id, payload, session, request, approved=True)


@router.post("/{approval_id}/reject", response_model=ApprovalRead)
async def reject(
    approval_id: uuid.UUID,
    payload: ApprovalDecision,
    session: SessionDependency,
    request: Request,
) -> ApprovalRead:
    return await _decide(approval_id, payload, session, request, approved=False)
