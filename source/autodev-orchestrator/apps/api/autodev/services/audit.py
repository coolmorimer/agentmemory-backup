from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from autodev.db.models import AuditEvent


def record_audit(
    session: AsyncSession,
    event: str,
    *,
    project_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    actor: str = "orchestrator",
    agent: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditEvent:
    audit = AuditEvent(
        event=event,
        project_id=project_id,
        task_id=task_id,
        actor=actor,
        agent=agent,
        details=details or {},
    )
    session.add(audit)
    return audit
