"""Create project, task, attempt, dependency, and audit foundation.

Revision ID: 20260903_0001
Revises:
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    privacy = sa.Enum("PUBLIC", "PRIVATE", "LOCAL_ONLY", name="privacy_level", native_enum=False)
    project_status = sa.Enum(
        "CREATED",
        "RESEARCHING",
        "PLANNING",
        "READY",
        "IMPLEMENTING",
        "TESTING",
        "REVIEWING",
        "STAGING",
        "VERIFYING_STAGING",
        "DEPLOYING",
        "VERIFYING_PRODUCTION",
        "COMPLETED",
        "BLOCKED",
        "FAILED",
        "PAUSED",
        name="project_status",
        native_enum=False,
    )
    task_status = sa.Enum(
        "DRAFT",
        "READY",
        "RUNNING",
        "WAITING_DEPENDENCY",
        "WAITING_PROVIDER",
        "TESTING",
        "REVIEWING",
        "FIX_REQUIRED",
        "APPROVED",
        "COMPLETED",
        "BLOCKED",
        "FAILED",
        "CANCELLED",
        name="task_status",
        native_enum=False,
    )
    risk = sa.Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="risk_level", native_enum=False)
    task_privacy = sa.Enum(
        "PUBLIC", "PRIVATE", "LOCAL_ONLY", name="task_privacy_level", native_enum=False
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("repository_path", sa.Text(), nullable=False),
        sa.Column("privacy_level", privacy, nullable=False),
        sa.Column("status", project_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_table(
        "goals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_goals_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_goals")),
    )
    op.create_index(op.f("ix_goals_project_id"), "goals", ["project_id"])
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("task_type", sa.String(length=80), nullable=False),
        sa.Column("status", task_status, nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("risk", risk, nullable=False),
        sa.Column("complexity", sa.Float(), nullable=False),
        sa.Column("privacy_level", task_privacy, nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), nullable=False),
        sa.Column("required_checks", sa.JSON(), nullable=False),
        sa.Column("context_requirements", sa.JSON(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_by", sa.String(length=200)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_tasks_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tasks")),
        sa.UniqueConstraint("project_id", "key", name="uq_tasks_project_key"),
    )
    op.create_index("ix_tasks_claim", "tasks", ["status", "next_run_at", "priority"])
    op.create_index(op.f("ix_tasks_project_id"), "tasks", ["project_id"])
    op.create_table(
        "task_dependencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("depends_on_task_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["depends_on_task_id"],
            ["tasks.id"],
            name=op.f("fk_task_dependencies_depends_on_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_dependencies_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_dependencies")),
        sa.UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependencies_pair"),
    )
    op.create_index(
        op.f("ix_task_dependencies_depends_on_task_id"), "task_dependencies", ["depends_on_task_id"]
    )
    op.create_index(op.f("ix_task_dependencies_task_id"), "task_dependencies", ["task_id"])
    op.create_table(
        "task_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("strategy_key", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("error_fingerprint", sa.String(length=128)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_task_attempts_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_task_attempts")),
        sa.UniqueConstraint("task_id", "number", name="uq_task_attempt_number"),
    )
    op.create_index(op.f("ix_task_attempts_task_id"), "task_attempts", ["task_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event", sa.String(length=120), nullable=False),
        sa.Column("project_id", sa.Uuid()),
        sa.Column("task_id", sa.Uuid()),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("agent", sa.String(length=200)),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_audit_events_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_audit_events_task_id_tasks"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_event"), "audit_events", ["event"])
    op.create_index(op.f("ix_audit_events_project_id"), "audit_events", ["project_id"])
    op.create_index(op.f("ix_audit_events_task_id"), "audit_events", ["task_id"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("task_attempts")
    op.drop_table("task_dependencies")
    op.drop_table("tasks")
    op.drop_table("goals")
    op.drop_table("projects")
