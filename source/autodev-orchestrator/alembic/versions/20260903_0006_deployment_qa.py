"""Add deployment, verification, incident, approval, and QA records.

Revision ID: 20260903_0006
Revises: 20260903_0005
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0006"
down_revision: str | None = "20260903_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "deployments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("environment", sa.String(length=40), nullable=False),
        sa.Column("adapter", sa.String(length=100), nullable=False),
        sa.Column("release_ref", sa.String(length=300), nullable=False),
        sa.Column("previous_release_ref", sa.String(length=300), nullable=True),
        sa.Column("external_id", sa.String(length=300), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("metadata", jsonb, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_deployments_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deployments")),
    )
    op.create_index(op.f("ix_deployments_project_id"), "deployments", ["project_id"])
    op.create_index(op.f("ix_deployments_environment"), "deployments", ["environment"])
    op.create_index(op.f("ix_deployments_status"), "deployments", ["status"])
    op.create_table(
        "deployment_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("deployment_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("artifact_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["deployment_id"],
            ["deployments.id"],
            name=op.f("fk_deployment_checks_deployment_id_deployments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_deployment_checks")),
    )
    op.create_index(
        op.f("ix_deployment_checks_deployment_id"), "deployment_checks", ["deployment_id"]
    )
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("deployment_id", sa.Uuid(), nullable=True),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", jsonb, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_incidents_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["deployment_id"],
            ["deployments.id"],
            name=op.f("fk_incidents_deployment_id_deployments"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
    )
    op.create_index(op.f("ix_incidents_project_id"), "incidents", ["project_id"])
    op.create_index(op.f("ix_incidents_deployment_id"), "incidents", ["deployment_id"])
    op.create_table(
        "approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("deployment_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(length=200), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_approvals_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["deployment_id"],
            ["deployments.id"],
            name=op.f("fk_approvals_deployment_id_deployments"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approvals")),
    )
    op.create_index(op.f("ix_approvals_project_id"), "approvals", ["project_id"])
    op.create_index(op.f("ix_approvals_deployment_id"), "approvals", ["deployment_id"])
    op.create_table(
        "qa_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("evidence", jsonb, nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_qa_findings_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.id"],
            name=op.f("fk_qa_findings_task_id_tasks"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qa_findings")),
    )
    op.create_index(op.f("ix_qa_findings_project_id"), "qa_findings", ["project_id"])
    op.create_index(op.f("ix_qa_findings_task_id"), "qa_findings", ["task_id"])
    op.create_index(op.f("ix_qa_findings_severity"), "qa_findings", ["severity"])


def downgrade() -> None:
    op.drop_table("qa_findings")
    op.drop_table("approvals")
    op.drop_table("incidents")
    op.drop_table("deployment_checks")
    op.drop_table("deployments")
