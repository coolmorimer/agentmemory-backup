"""Add editable provider, model, and routing configuration.

Revision ID: 20260903_0007
Revises: 20260903_0006
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0007"
down_revision: str | None = "20260903_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table(
        "provider_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("api_key_env", sa.String(length=120), nullable=True),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("billing_mode", sa.String(length=40), nullable=False),
        sa.Column("accepts_private_code", sa.Boolean(), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_configs")),
        sa.UniqueConstraint("name", name=op.f("uq_provider_configs_name")),
    )
    op.create_index(op.f("ix_provider_configs_name"), "provider_configs", ["name"])
    op.create_table(
        "model_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_id", sa.String(length=300), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=300), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("local", sa.Boolean(), nullable=False),
        sa.Column("installed", sa.Boolean(), nullable=False),
        sa.Column("capabilities", jsonb, nullable=False),
        sa.Column("roles", jsonb, nullable=False),
        sa.Column("max_context", sa.Integer(), nullable=False),
        sa.Column("quality", sa.Float(), nullable=False),
        sa.Column("reliability", sa.Float(), nullable=False),
        sa.Column("expected_latency_seconds", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_configs")),
        sa.UniqueConstraint("model_id", name=op.f("uq_model_configs_model_id")),
    )
    op.create_index(op.f("ix_model_configs_model_id"), "model_configs", ["model_id"])
    op.create_index(op.f("ix_model_configs_provider"), "model_configs", ["provider"])
    op.create_table(
        "routing_preferences",
        sa.Column("role", sa.String(length=80), nullable=False),
        sa.Column("model_id", sa.String(length=300), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("role", name=op.f("pk_routing_preferences")),
    )


def downgrade() -> None:
    op.drop_table("routing_preferences")
    op.drop_table("model_configs")
    op.drop_table("provider_configs")
