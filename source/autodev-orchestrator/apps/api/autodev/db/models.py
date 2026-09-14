from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from autodev.db.base import Base, utcnow
from autodev.domain.enums import PrivacyLevel, ProjectStatus, RiskLevel, TaskStatus

JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")


def enum_column(enum_type: type[Any], name: str) -> SAEnum:
    return SAEnum(
        enum_type,
        name=name,
        native_enum=False,
        validate_strings=True,
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    repository_path: Mapped[str] = mapped_column(Text, nullable=False)
    privacy_level: Mapped[PrivacyLevel] = mapped_column(
        enum_column(PrivacyLevel, "privacy_level"), default=PrivacyLevel.PRIVATE, nullable=False
    )
    status: Mapped[ProjectStatus] = mapped_column(
        enum_column(ProjectStatus, "project_status"), default=ProjectStatus.CREATED, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    goals: Mapped[list[Goal]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tasks: Mapped[list[Task]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="goals")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("project_id", "key", name="uq_tasks_project_key"),
        Index("ix_tasks_claim", "status", "next_run_at", "priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    task_type: Mapped[str] = mapped_column(String(80), default="implementation", nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        enum_column(TaskStatus, "task_status"), default=TaskStatus.DRAFT, nullable=False
    )
    priority: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    risk: Mapped[RiskLevel] = mapped_column(
        enum_column(RiskLevel, "risk_level"), default=RiskLevel.MEDIUM, nullable=False
    )
    complexity: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    privacy_level: Mapped[PrivacyLevel] = mapped_column(
        enum_column(PrivacyLevel, "task_privacy_level"),
        default=PrivacyLevel.PRIVATE,
        nullable=False,
    )
    acceptance_criteria: Mapped[list[str]] = mapped_column(
        JSON_DOCUMENT, default=list, nullable=False
    )
    required_checks: Mapped[list[list[str]]] = mapped_column(
        JSON_DOCUMENT, default=list, nullable=False
    )
    context_requirements: Mapped[dict[str, Any]] = mapped_column(
        JSON_DOCUMENT, default=dict, nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    claimed_by: Mapped[str | None] = mapped_column(String(200))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    project: Mapped[Project] = relationship(back_populates="tasks")
    attempts: Mapped[list[TaskAttempt]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependencies_pair"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    depends_on_task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )


class TaskAttempt(Base):
    __tablename__ = "task_attempts"
    __table_args__ = (UniqueConstraint("task_id", "number", name="uq_task_attempt_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="RUNNING", nullable=False)
    error_fingerprint: Mapped[str | None] = mapped_column(String(128))
    result: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    task: Mapped[Task] = relationship(back_populates="attempts")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    actor: Mapped[str] = mapped_column(String(120), default="orchestrator", nullable=False)
    agent: Mapped[str | None] = mapped_column(String(200))
    details: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_DOCUMENT, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class CheckRun(Base):
    __tablename__ = "check_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    command: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, nullable=False)
    exit_code: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ReviewRecord(Base):
    __tablename__ = "review_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewer: Mapped[str] = mapped_column(String(200), nullable=False)
    approved: Mapped[bool] = mapped_column(nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_DOCUMENT, default=list, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class GitCommit(Base):
    __tablename__ = "git_commits"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sha: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    repository_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ProviderQuotaSnapshot(Base):
    __tablename__ = "quota_snapshots"
    __table_args__ = (
        UniqueConstraint("provider", "model", "window", name="uq_quota_provider_model_window"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    window: Mapped[str] = mapped_column(String(100), default="rolling", nullable=False)
    requests_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requests_remaining: Mapped[int | None] = mapped_column(Integer)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_remaining: Mapped[int | None] = mapped_column(Integer)
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(40), default="estimated", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ModelHealthRecord(Base):
    __tablename__ = "model_health"
    __table_args__ = (UniqueConstraint("provider", "model", name="uq_model_health_provider_model"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(40), default="HEALTHY", nullable=False)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ModelUsageRecord(Base):
    __tablename__ = "model_usage"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(300), nullable=False, index=True)
    prompt_version: Mapped[str] = mapped_column(String(100), default="unknown", nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_seconds: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class ProviderConfigRecord(Base):
    __tablename__ = "provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    api_key_env: Mapped[str | None] = mapped_column(String(120))
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    billing_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    accepts_private_code: Mapped[bool] = mapped_column(default=False, nullable=False)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=60, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ModelConfigRecord(Base):
    __tablename__ = "model_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    model_id: Mapped[str] = mapped_column(String(300), nullable=False, unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    local: Mapped[bool] = mapped_column(default=False, nullable=False)
    installed: Mapped[bool] = mapped_column(default=False, nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list, nullable=False)
    roles: Mapped[list[str]] = mapped_column(JSON_DOCUMENT, default=list, nullable=False)
    max_context: Mapped[int] = mapped_column(Integer, default=16_384, nullable=False)
    quality: Mapped[float] = mapped_column(Float, default=0.7, nullable=False)
    reliability: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)
    expected_latency_seconds: Mapped[float] = mapped_column(Float, default=10, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class RoutingPreferenceRecord(Base):
    __tablename__ = "routing_preferences"

    role: Mapped[str] = mapped_column(String(80), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(300), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class CodexThreadRecord(Base):
    __tablename__ = "codex_threads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    thread_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(40), default="ACTIVE", nullable=False)
    last_turn_id: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class CodexTurnRecord(Base):
    __tablename__ = "codex_turns"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    turn_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class DeploymentRecord(Base):
    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    environment: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    adapter: Mapped[str] = mapped_column(String(100), nullable=False)
    release_ref: Mapped[str] = mapped_column(String(300), nullable=False)
    previous_release_ref: Mapped[str | None] = mapped_column(String(300))
    external_id: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    details: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_DOCUMENT, default=dict, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeploymentCheckRecord(Base):
    __tablename__ = "deployment_checks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    passed: Mapped[bool] = mapped_column(nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)
    artifact_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )


class IncidentRecord(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="SET NULL"), index=True
    )
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="OPEN", nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalRecord(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="PENDING", nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(200))
    reason: Mapped[str | None] = mapped_column(Text)


class QaFindingRecord(Base):
    __tablename__ = "qa_findings"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    severity: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON_DOCUMENT, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="OPEN", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
