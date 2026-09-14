"""Add durable execution checks, reviews, commit links, and attempt results.

Revision ID: 20260903_0002
Revises: 20260903_0001
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0002"
down_revision: str | None = "20260903_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "task_attempts",
        sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
    )
    op.alter_column("task_attempts", "result", server_default=None)
    op.create_table(
        "check_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("command", sa.JSON(), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=False),
        sa.Column("output_tail", sa.Text(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_check_runs_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_check_runs")),
    )
    op.create_index(op.f("ix_check_runs_task_id"), "check_runs", ["task_id"])
    op.create_table(
        "review_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("reviewer", sa.String(length=200), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_review_records_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_review_records")),
    )
    op.create_index(op.f("ix_review_records_task_id"), "review_records", ["task_id"])
    op.create_table(
        "git_commits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("sha", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("repository_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_git_commits_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_git_commits")),
        sa.UniqueConstraint("sha", name=op.f("uq_git_commits_sha")),
    )
    op.create_index(op.f("ix_git_commits_task_id"), "git_commits", ["task_id"])


def downgrade() -> None:
    op.drop_table("git_commits")
    op.drop_table("review_records")
    op.drop_table("check_runs")
    op.drop_column("task_attempts", "result")
