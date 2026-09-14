from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from autodev.db.models import Project, QaFindingRecord, Task
from autodev.domain.enums import RiskLevel, TaskStatus
from autodev.qa.browser import BrowserQaResult
from autodev.services.audit import record_audit


@dataclass(frozen=True, slots=True)
class QaFailureRecords:
    finding: QaFindingRecord
    fix_task: Task


class QaEvidenceService:
    async def record_browser_result(
        self,
        session: AsyncSession,
        *,
        project_id: uuid.UUID,
        task_id: uuid.UUID | None,
        result: BrowserQaResult,
    ) -> QaFailureRecords | None:
        if result.passed:
            record_audit(
                session,
                "qa.browser.passed",
                project_id=project_id,
                task_id=task_id,
                details={"artifacts": result.artifacts},
            )
            return None
        project = await session.get(Project, project_id)
        if project is None:
            raise LookupError(f"project not found: {project_id}")
        source_task = await session.get(Task, task_id) if task_id else None
        finding_id = uuid.uuid4()
        finding = QaFindingRecord(
            id=finding_id,
            project_id=project_id,
            task_id=task_id,
            severity="HIGH" if result.console_errors or result.failed_requests else "MEDIUM",
            title="Browser QA flow failed",
            evidence={
                "console_errors": result.console_errors,
                "failed_requests": result.failed_requests,
                "artifacts": result.artifacts,
                "output_tail": result.output[-16_000:],
            },
            status="OPEN",
        )
        fix_task = Task(
            project_id=project_id,
            key=f"QA-{finding_id.hex[:12].upper()}",
            title="Fix browser QA failure",
            description=(
                "Resolve the linked browser QA finding, then rerun the same Playwright flow."
            ),
            task_type="qa_fix",
            status=TaskStatus.READY,
            priority=90,
            risk=RiskLevel.HIGH,
            complexity=0.6,
            privacy_level=source_task.privacy_level if source_task else project.privacy_level,
            acceptance_criteria=[
                "Browser flow passes without console errors or failed HTTP requests.",
                "Failure artifacts are reviewed and the QA finding can be resolved.",
            ],
            required_checks=[],
            context_requirements={
                "qa_finding_id": str(finding_id),
                "artifacts": result.artifacts,
            },
        )
        session.add_all([finding, fix_task])
        record_audit(
            session,
            "qa.browser.failed",
            project_id=project_id,
            task_id=task_id,
            details={"finding_id": str(finding_id), "fix_task_key": fix_task.key},
        )
        await session.flush()
        return QaFailureRecords(finding=finding, fix_task=fix_task)
