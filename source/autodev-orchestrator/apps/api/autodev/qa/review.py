from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from autodev.qa.checks import CheckResult


class ReviewIssue(BaseModel):
    severity: Literal["low", "medium", "high", "critical"]
    file: str | None = None
    line: int | None = None
    problem: str
    required_fix: str


class ReviewResult(BaseModel):
    approved: bool
    confidence: float = Field(ge=0, le=1)
    issues: list[ReviewIssue] = Field(default_factory=list)
    reviewer: str


class Reviewer(Protocol):
    async def review(
        self, *, diff: str, changed_files: list[str], checks: list[CheckResult]
    ) -> ReviewResult: ...


class DeterministicReviewer:
    async def review(
        self, *, diff: str, changed_files: list[str], checks: list[CheckResult]
    ) -> ReviewResult:
        issues: list[ReviewIssue] = []
        if not changed_files or not diff.strip():
            issues.append(
                ReviewIssue(
                    severity="high",
                    problem="The coding task produced no reviewable Git diff.",
                    required_fix="Produce a scoped implementation diff.",
                )
            )
        if not checks:
            issues.append(
                ReviewIssue(
                    severity="high",
                    problem="No deterministic checks were configured.",
                    required_fix="Configure and run at least one relevant check.",
                )
            )
        for check in checks:
            if not check.passed:
                issues.append(
                    ReviewIssue(
                        severity="high",
                        problem=f"Required check failed with exit code {check.exit_code}.",
                        required_fix="Fix the failure and rerun the required check.",
                    )
                )
        return ReviewResult(
            approved=not issues,
            confidence=1.0,
            issues=issues,
            reviewer="deterministic-v1",
        )
