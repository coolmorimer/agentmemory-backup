"""Use PostgreSQL JSONB for durable document fields.

Revision ID: 20260903_0003
Revises: 20260903_0002
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0003"
down_revision: str | None = "20260903_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DOCUMENT_COLUMNS = {
    "tasks": ("acceptance_criteria", "required_checks", "context_requirements"),
    "task_attempts": ("result",),
    "audit_events": ("metadata",),
    "check_runs": ("command",),
    "review_records": ("issues",),
}


def upgrade() -> None:
    for table, columns in DOCUMENT_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                type_=postgresql.JSONB(astext_type=sa.Text()),
                postgresql_using=f"{column}::jsonb",
            )


def downgrade() -> None:
    for table, columns in DOCUMENT_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                type_=sa.JSON(),
                postgresql_using=f"{column}::json",
            )
