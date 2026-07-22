"""add persisted tool registry configuration

Revision ID: 202607210008
Revises: 202607210007
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607210008"
down_revision: str | None = "202607210007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tool_configurations",
        sa.Column("tool_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=40), nullable=False),
        sa.Column("target_types", sa.JSON(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tool_configurations")),
        sa.UniqueConstraint("tool_name", name=op.f("uq_tool_configurations_tool_name")),
    )
    op.create_index(op.f("ix_tool_configurations_tool_name"), "tool_configurations", ["tool_name"], unique=True)
    op.create_index(op.f("ix_tool_configurations_risk_level"), "tool_configurations", ["risk_level"], unique=False)
    op.create_index(op.f("ix_tool_configurations_is_enabled"), "tool_configurations", ["is_enabled"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_tool_configurations_is_enabled"), table_name="tool_configurations")
    op.drop_index(op.f("ix_tool_configurations_risk_level"), table_name="tool_configurations")
    op.drop_index(op.f("ix_tool_configurations_tool_name"), table_name="tool_configurations")
    op.drop_table("tool_configurations")
