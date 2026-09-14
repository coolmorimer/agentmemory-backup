from sqlalchemy import select

from autodev.db.models import Project, QaFindingRecord, Task
from autodev.db.session import Database
from autodev.qa.browser import BrowserQaResult
from autodev.qa.evidence import QaEvidenceService


async def test_failed_browser_qa_creates_finding_and_ready_fix_task(database: Database) -> None:
    async with database.session() as session:
        project = Project(name="browser", repository_path="C:/fixture")
        session.add(project)
        await session.commit()
        project_id = project.id

    result = BrowserQaResult(
        passed=False,
        commands_run=["open", "screenshot"],
        console_errors=["TypeError: broken"],
        failed_requests=["GET /api 500"],
        artifacts=["output/playwright/failure/page.png", "output/playwright/failure/trace.zip"],
        output="failure detail",
    )
    async with database.session() as session:
        records = await QaEvidenceService().record_browser_result(
            session, project_id=project_id, task_id=None, result=result
        )
        await session.commit()

    assert records is not None
    assert records.finding.severity == "HIGH"
    assert records.fix_task.status.value == "READY"
    assert records.fix_task.context_requirements["qa_finding_id"] == str(records.finding.id)
    async with database.session() as session:
        findings = list(await session.scalars(select(QaFindingRecord)))
        tasks = list(await session.scalars(select(Task)))
    assert len(findings) == len(tasks) == 1
