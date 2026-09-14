"""Add durable provider quota, health, and usage records.

Revision ID: 20260903_0004
Revises: 20260903_0003
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0004"
down_revision: str | None = "20260903_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quota_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=300), nullable=False),
        sa.Column("window", sa.String(length=100), nullable=False),
        sa.Column("requests_used", sa.Integer(), nullable=False),
        sa.Column("requests_remaining", sa.Integer(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=False),
        sa.Column("tokens_remaining", sa.Integer(), nullable=True),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_quota_snapshots")),
        sa.UniqueConstraint(
            "provider",
            "model",
            "window",
            name="uq_quota_provider_model_window",
        ),
    )
    op.create_index(op.f("ix_quota_snapshots_provider"), "quota_snapshots", ["provider"])
    op.create_index(op.f("ix_quota_snapshots_model"), "quota_snapshots", ["model"])
    op.create_table(
        "model_health",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=300), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_health")),
        sa.UniqueConstraint("provider", "model", name="uq_model_health_provider_model"),
    )
    op.create_index(op.f("ix_model_health_provider"), "model_health", ["provider"])
    op.create_index(op.f("ix_model_health_model"), "model_health", ["model"])
    op.create_table(
        "model_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=300), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("latency_seconds", sa.Float(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_model_usage_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_model_usage_task_id_tasks"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_usage")),
    )
    op.create_index(op.f("ix_model_usage_provider"), "model_usage", ["provider"])
    op.create_index(op.f("ix_model_usage_model"), "model_usage", ["model"])
    op.create_index(op.f("ix_model_usage_project_id"), "model_usage", ["project_id"])
    op.create_index(op.f("ix_model_usage_task_id"), "model_usage", ["task_id"])


def downgrade() -> None:
    op.drop_table("model_usage")
    op.drop_table("model_health")
    op.drop_table("quota_snapshots")
