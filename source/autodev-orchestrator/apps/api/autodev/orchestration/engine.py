from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autodev.codex.base import CodingAgent, CodingResult, CodingTask
from autodev.db.models import (
    CheckRun,
    CodexThreadRecord,
    CodexTurnRecord,
    GitCommit,
    Project,
    ReviewRecord,
    Task,
    TaskAttempt,
)
from autodev.db.session import Database
from autodev.domain.enums import ProjectStatus, TaskStatus
from autodev.domain.fsm import ProjectStateMachine, TaskStateMachine
from autodev.git.repository import GitCommitResult, GitError, GitRepository
from autodev.memory.base import MemoryProvider, MemoryQuery, MemoryRecord, MemoryScope
from autodev.orchestration.advisor import ImplementationAdvisor
from autodev.qa.checks import CheckResult, CheckRunner
from autodev.qa.review import DeterministicReviewer, Reviewer, ReviewResult
from autodev.repository.context import ContextBuilder, ContextRequest
from autodev.repository.intelligence import RepoIntelligence
from autodev.routing.models import RoutingDecision, TaskRequirements
from autodev.routing.router import ModelRouter
from autodev.services.audit import record_audit


class ExecutionResult(BaseModel):
    task_id: uuid.UUID
    status: TaskStatus
    route: RoutingDecision
    coding: CodingResult
    checks: list[CheckResult] = Field(default_factory=list)
    review: ReviewResult | None = None
    commit: GitCommitResult | None = None


class ExecutionEngine:
    def __init__(
        self,
        database: Database,
        *,
        router: ModelRouter,
        coding_agent: CodingAgent,
        check_runner: CheckRunner | None = None,
        reviewer: Reviewer | None = None,
        memory_provider: MemoryProvider | None = None,
        router_resolver: Callable[[AsyncSession], Awaitable[ModelRouter]] | None = None,
        preference_resolver: Callable[[AsyncSession, str], Awaitable[str | None]] | None = None,
        implementation_advisor: ImplementationAdvisor | None = None,
    ) -> None:
        self._database = database
        self._router = router
        self._coding_agent = coding_agent
        self._check_runner = check_runner or CheckRunner()
        self._reviewer = reviewer or DeterministicReviewer()
        self._memory_provider = memory_provider
        self._router_resolver = router_resolver
        self._preference_resolver = preference_resolver
        self._implementation_advisor = implementation_advisor
        self._task_fsm = TaskStateMachine()
        self._project_fsm = ProjectStateMachine()
        self._integration_lock = asyncio.Lock()

    async def execute_claimed(self, task_id: uuid.UUID) -> ExecutionResult:
        async with self._database.session() as session:
            task = await session.get(Task, task_id)
            if task is None:
                raise LookupError(f"task not found: {task_id}")
            if task.status is not TaskStatus.RUNNING:
                raise ValueError(f"task must be RUNNING, got {task.status.value}")
            project = await session.get(Project, task.project_id)
            if project is None:
                raise LookupError(f"project not found: {task.project_id}")
            repository_path = Path(project.repository_path)
            raw_model_override = task.context_requirements.get("model_override")
            model_override = raw_model_override if isinstance(raw_model_override, str) else None
            if model_override is None and self._preference_resolver is not None:
                model_override = await self._preference_resolver(session, task.task_type)
            router = await self._router_resolver(session) if self._router_resolver else self._router
            route = router.route(
                TaskRequirements(
                    task_type=task.task_type,
                    complexity=task.complexity,
                    privacy_level=task.privacy_level,
                    requires_structured_output=True,
                ),
                preferred_model_id=model_override,
            )
            codex_thread = await session.scalar(
                select(CodexThreadRecord).where(CodexThreadRecord.task_id == task.id)
            )
            coding_task = CodingTask(
                task_id=task.id,
                key=task.key,
                title=task.title,
                description=task.description,
                repository_path=repository_path,
                acceptance_criteria=task.acceptance_criteria,
                required_checks=task.required_checks,
                thread_id=codex_thread.thread_id if codex_thread else None,
            )
            attempt_number = task.attempt_count

            previous_attempt = await session.scalar(
                select(TaskAttempt)
                .where(
                    TaskAttempt.task_id == task.id,
                    TaskAttempt.number < attempt_number,
                )
                .order_by(TaskAttempt.number.desc())
                .limit(1)
            )
            previous_summary = (
                json.dumps(previous_attempt.result, default=str)[-4000:]
                if previous_attempt is not None
                else ""
            )

        execution_path, task_branch, worktree_name = await self._prepare_worktree(
            repository_path,
            task_id=task.id,
            task_key=task.key,
        )
        coding_task.repository_path = execution_path

        memories = []
        if self._memory_provider is not None:
            seen_memory_ids: set[str] = set()
            for memory_project in (project.name, None):
                try:
                    found = await self._memory_provider.search(
                        MemoryQuery(
                            query=f"{coding_task.title}\n{coding_task.description}",
                            project=memory_project,
                            limit=5,
                        )
                    )
                except Exception:
                    continue
                for item in found:
                    if item.id not in seen_memory_ids:
                        memories.append(item)
                        seen_memory_ids.add(item.id)
        raw_files = task.context_requirements.get("files", [])
        relevant_files = (
            [item for item in raw_files if isinstance(item, str)]
            if isinstance(raw_files, list)
            else []
        )
        repository_map = await asyncio.to_thread(RepoIntelligence(execution_path).scan)
        context_request = ContextRequest(
            task_key=coding_task.key,
            title=coding_task.title,
            description=coding_task.description,
            acceptance_criteria=coding_task.acceptance_criteria,
            relevant_files=relevant_files,
            previous_attempt_summary=previous_summary,
        )
        context_bundle = await asyncio.to_thread(
            ContextBuilder(execution_path).build,
            context_request,
            repository_map,
            memories=memories,
        )
        coding_task.context = context_bundle.content

        if self._implementation_advisor is not None:
            advice = await self._implementation_advisor.advise(
                route,
                project_id=project.id,
                task_id=task.id,
                title=coding_task.title,
                description=coding_task.description,
                context=coding_task.context,
            )
            if advice:
                coding_task.context += (
                    "\n\n<selected_model_advice trust=\"untrusted\">\n"
                    f"{advice[-12_000:]}\n"
                    "</selected_model_advice>"
                )

        coding = await self._coding_agent.run_task(coding_task)
        checks: list[CheckResult] = []
        review: ReviewResult | None = None
        commit: GitCommitResult | None = None

        if coding.status == "completed":
            checks = await self._check_runner.run(execution_path, coding_task.required_checks)
            repository = GitRepository(execution_path)
            changed_files = await repository.changed_files()
            diff = await repository.diff()
            review = await self._reviewer.review(
                diff=diff, changed_files=changed_files, checks=checks
            )
            if review.approved and not await self._task_is_interrupted(task_id):
                try:
                    candidate_commit = await repository.commit_task(
                        task_key=coding_task.key,
                        title=coding_task.title,
                        changed_files=changed_files,
                        checks=[" ".join(result.command) for result in checks],
                    )
                    commit, checks = await self._integrate_worktree(
                        repository_path,
                        execution_path,
                        task_branch=task_branch,
                        worktree_name=worktree_name,
                        commit=candidate_commit,
                        required_checks=coding_task.required_checks,
                        checks=checks,
                    )
                except GitError as error:
                    review = ReviewResult(
                        approved=False,
                        confidence=1,
                        reviewer="git-integration",
                        issues=[
                            {
                                "severity": "high",
                                "problem": str(error),
                                "required_fix": "Repair the Git integration and retry the task.",
                            }
                        ],
                    )

        status = await self._persist_result(
            task_id=task_id,
            attempt_number=attempt_number,
            route=route,
            coding=coding,
            checks=checks,
            review=review,
            commit=commit,
            repository_path=repository_path,
        )
        if status is TaskStatus.COMPLETED and self._memory_provider is not None:
            try:
                await self._memory_provider.store(
                    MemoryRecord(
                        content=(
                            f"Task {coding_task.key} completed: {coding.summary}. "
                            f"Checks: {len(checks)}; commit: {commit.sha if commit else 'none'}."
                        ),
                        scope=MemoryScope.EXPERIENCE,
                        project=project.name,
                        concepts=[coding_task.key, "verified-task-completion", route.model_id],
                        files=coding.changed_files,
                        memory_type="task_outcome",
                    )
                )
            except Exception:
                await self._record_memory_failure(task_id)
        return ExecutionResult(
            task_id=task_id,
            status=status,
            route=route,
            coding=coding,
            checks=checks,
            review=review,
            commit=commit,
        )

    async def _prepare_worktree(
        self, repository_path: Path, *, task_id: uuid.UUID, task_key: str
    ) -> tuple[Path, str, str]:
        repository = GitRepository(repository_path)
        safe_key = "".join(character if character.isalnum() else "-" for character in task_key)
        suffix = task_id.hex[:8]
        worktree_name = f"task-{suffix}"
        task_branch = f"autodev/{safe_key.lower()}-{suffix}"
        worktree_path = (repository.worktree_root / worktree_name).resolve()
        async with self._integration_lock:
            if worktree_path.is_dir():
                worktree_repository = GitRepository(worktree_path)
                if not await worktree_repository.is_repository():
                    raise GitError(
                        f"existing task worktree is not a Git repository: {worktree_path}"
                    )
                return worktree_path, task_branch, worktree_name
            worktree = await repository.create_worktree(
                worktree_name,
                branch=task_branch,
                create_branch=not await repository.branch_exists(task_branch),
            )
        return worktree.path, task_branch, worktree_name

    async def _integrate_worktree(
        self,
        repository_path: Path,
        execution_path: Path,
        *,
        task_branch: str,
        worktree_name: str,
        commit: GitCommitResult,
        required_checks: list[list[str]],
        checks: list[CheckResult],
    ) -> tuple[GitCommitResult, list[CheckResult]]:
        root = GitRepository(repository_path)
        task_repository = GitRepository(execution_path)
        async with self._integration_lock:
            root_status = await root.status()
            if not root_status.clean:
                raise GitError("main repository has unrelated changes; task branch was preserved")
            try:
                await root.merge(task_branch, fast_forward_only=True)
            except GitError as merge_error:
                if root_status.head_sha is None:
                    raise
                await task_repository.rebase(root_status.head_sha)
                checks = await self._check_runner.run(execution_path, required_checks)
                if not checks or any(not check.passed for check in checks):
                    raise GitError("checks failed after rebasing task branch") from merge_error
                rebased_status = await task_repository.status()
                if rebased_status.head_sha is None:
                    raise GitError("rebased task branch has no commit") from merge_error
                commit = GitCommitResult(
                    sha=rebased_status.head_sha,
                    message=commit.message,
                    changed_files=commit.changed_files,
                )
                await root.merge(task_branch, fast_forward_only=True)
            with suppress(GitError):
                await root.remove_worktree(worktree_name)
        return commit, checks

    async def _record_memory_failure(self, task_id: uuid.UUID) -> None:
        async with self._database.session() as session, session.begin():
            task = await session.get(Task, task_id)
            if task is not None:
                record_audit(
                    session,
                    "memory.store.failed",
                    project_id=task.project_id,
                    task_id=task.id,
                )

    async def _task_is_interrupted(self, task_id: uuid.UUID) -> bool:
        async with self._database.session() as session:
            status = await session.scalar(select(Task.status).where(Task.id == task_id))
        return status in {TaskStatus.CANCELLED, TaskStatus.PAUSED}

    async def _persist_result(
        self,
        *,
        task_id: uuid.UUID,
        attempt_number: int,
        route: RoutingDecision,
        coding: CodingResult,
        checks: list[CheckResult],
        review: ReviewResult | None,
        commit: GitCommitResult | None,
        repository_path: Path,
    ) -> TaskStatus:
        async with self._database.session() as session, session.begin():
            task = await session.get(Task, task_id, with_for_update=True)
            if task is None:
                raise LookupError(f"task not found: {task_id}")
            attempt = await session.scalar(
                select(TaskAttempt).where(
                    TaskAttempt.task_id == task_id,
                    TaskAttempt.number == attempt_number,
                )
            )
            if attempt is None:
                raise LookupError(f"attempt not found: {task_id}/{attempt_number}")

            if task.status in {TaskStatus.CANCELLED, TaskStatus.PAUSED}:
                interrupted_status = task.status
                attempt.status = interrupted_status.value
                attempt.finished_at = datetime.now(UTC)
                task.claimed_by = None
                task.lease_expires_at = None
                record_audit(
                    session,
                    "task.execution.discarded",
                    project_id=task.project_id,
                    task_id=task.id,
                    details={"reason": interrupted_status.value.lower()},
                )
                return interrupted_status

            record_audit(
                session,
                "model.route.selected",
                project_id=task.project_id,
                task_id=task.id,
                details=route.model_dump(mode="json"),
            )
            attempt.result = {
                "route": route.model_dump(mode="json"),
                "coding": coding.model_dump(mode="json"),
                "checks": [item.model_dump(mode="json") for item in checks],
                "review": review.model_dump(mode="json") if review else None,
                "commit": commit.model_dump(mode="json") if commit else None,
            }
            attempt.finished_at = datetime.now(UTC)
            await self._record_codex_execution(session, task, coding)

            if coding.status != "completed":
                target = (
                    TaskStatus.FAILED
                    if task.attempt_count >= task.max_attempts
                    else TaskStatus.FIX_REQUIRED
                )
                task.status = self._task_fsm.transition(task.status, target)
                attempt.status = target.value
                record_audit(
                    session,
                    "task.execution.failed",
                    project_id=task.project_id,
                    task_id=task.id,
                    details={"error": coding.error or "coding agent failed"},
                )
                return task.status

            task.status = self._task_fsm.transition(task.status, TaskStatus.TESTING)
            for check in checks:
                session.add(
                    CheckRun(
                        task_id=task.id,
                        attempt_number=attempt_number,
                        command=check.command,
                        exit_code=check.exit_code,
                        output_tail=check.output[-16_000:],
                        duration_seconds=check.duration_seconds,
                        passed=check.passed,
                    )
                )
            if not checks or any(not check.passed for check in checks):
                task.status = self._task_fsm.transition(task.status, TaskStatus.FIX_REQUIRED)
                attempt.status = TaskStatus.FIX_REQUIRED.value
                record_audit(
                    session,
                    "task.tests.failed",
                    project_id=task.project_id,
                    task_id=task.id,
                )
                return task.status

            task.status = self._task_fsm.transition(task.status, TaskStatus.REVIEWING)
            if review is None:
                raise RuntimeError("completed checks require a review result")
            session.add(
                ReviewRecord(
                    task_id=task.id,
                    attempt_number=attempt_number,
                    reviewer=review.reviewer,
                    approved=review.approved,
                    confidence=review.confidence,
                    issues=[issue.model_dump(mode="json") for issue in review.issues],
                )
            )
            if not review.approved or commit is None:
                task.status = self._task_fsm.transition(task.status, TaskStatus.FIX_REQUIRED)
                attempt.status = TaskStatus.FIX_REQUIRED.value
                record_audit(
                    session,
                    "task.review.rejected",
                    project_id=task.project_id,
                    task_id=task.id,
                    details={"issues": len(review.issues)},
                )
                return task.status

            task.status = self._task_fsm.transition(task.status, TaskStatus.APPROVED)
            task.status = self._task_fsm.transition(task.status, TaskStatus.COMPLETED)
            task.completed_at = datetime.now(UTC)
            task.claimed_by = None
            task.lease_expires_at = None
            attempt.status = TaskStatus.COMPLETED.value
            session.add(
                GitCommit(
                    task_id=task.id,
                    sha=commit.sha,
                    message=commit.message,
                    repository_path=str(repository_path),
                )
            )
            record_audit(
                session,
                "task.completed",
                project_id=task.project_id,
                task_id=task.id,
                details={"commit": commit.sha},
            )
            await self._complete_project_if_ready(session, task)
            return task.status

    @staticmethod
    async def _record_codex_execution(
        session: AsyncSession, task: Task, coding: CodingResult
    ) -> None:
        if not coding.thread_id:
            return
        thread = await session.scalar(
            select(CodexThreadRecord).where(CodexThreadRecord.task_id == task.id)
        )
        if thread is None:
            thread = CodexThreadRecord(task_id=task.id, thread_id=coding.thread_id)
            session.add(thread)
        thread.status = "ACTIVE" if coding.status == "completed" else coding.status.upper()
        thread.last_turn_id = coding.turn_id
        if coding.turn_id:
            existing_turn = await session.scalar(
                select(CodexTurnRecord).where(CodexTurnRecord.turn_id == coding.turn_id)
            )
            if existing_turn is None:
                session.add(
                    CodexTurnRecord(
                        task_id=task.id,
                        thread_id=coding.thread_id,
                        turn_id=coding.turn_id,
                        status=coding.status.upper(),
                        summary=coding.summary[-16_000:],
                        error=coding.error[-4000:] if coding.error else None,
                    )
                )

    async def _complete_project_if_ready(self, session: AsyncSession, completed_task: Task) -> None:
        remaining = await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(
                Task.project_id == completed_task.project_id,
                Task.id != completed_task.id,
                Task.status != TaskStatus.COMPLETED,
            )
        )
        if remaining:
            return
        project = await session.get(Project, completed_task.project_id, with_for_update=True)
        if project is None or project.status is not ProjectStatus.IMPLEMENTING:
            return
        project.status = self._project_fsm.transition(project.status, ProjectStatus.TESTING)
        project.status = self._project_fsm.transition(project.status, ProjectStatus.REVIEWING)
        project.status = self._project_fsm.transition(project.status, ProjectStatus.COMPLETED)
        record_audit(session, "project.completed", project_id=project.id)
