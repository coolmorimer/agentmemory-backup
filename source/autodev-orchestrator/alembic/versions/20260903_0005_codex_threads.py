"""Persist Codex App Server threads and turns.

Revision ID: 20260903_0005
Revises: 20260903_0004
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0005"
down_revision: str | None = "20260903_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "codex_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("last_turn_id", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_codex_threads_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_codex_threads")),
        sa.UniqueConstraint("task_id", name=op.f("uq_codex_threads_task_id")),
        sa.UniqueConstraint("thread_id", name=op.f("uq_codex_threads_thread_id")),
    )
    op.create_index(op.f("ix_codex_threads_task_id"), "codex_threads", ["task_id"])
    op.create_table(
        "codex_turns",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.String(length=200), nullable=False),
        sa.Column("turn_id", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_codex_turns_task_id_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_codex_turns")),
        sa.UniqueConstraint("turn_id", name=op.f("uq_codex_turns_turn_id")),
    )
    op.create_index(op.f("ix_codex_turns_task_id"), "codex_turns", ["task_id"])
    op.create_index(op.f("ix_codex_turns_thread_id"), "codex_turns", ["thread_id"])


def downgrade() -> None:
    op.drop_table("codex_turns")
    op.drop_table("codex_threads")
