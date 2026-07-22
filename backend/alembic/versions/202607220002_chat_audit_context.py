"""add exact AI provider context to audit records

Revision ID: 202607220002
Revises: 202607220001
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607220002"
down_revision: str | None = "202607220001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.add_column(sa.Column("provider_input", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("provider", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("model", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("request_id", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("context_sources", sa.JSON(), nullable=False,
                                      server_default="[]"))
        batch_op.add_column(sa.Column("tool_events", sa.JSON(), nullable=False,
                                      server_default="[]"))
        batch_op.add_column(sa.Column("integrity_version", sa.Integer(), nullable=False,
                                      server_default="1"))
        batch_op.create_index("ix_audit_logs_provider", ["provider"])
        batch_op.create_index("ix_audit_logs_request_id", ["request_id"])


def downgrade() -> None:
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.drop_index("ix_audit_logs_request_id")
        batch_op.drop_index("ix_audit_logs_provider")
        batch_op.drop_column("integrity_version")
        batch_op.drop_column("tool_events")
        batch_op.drop_column("context_sources")
        batch_op.drop_column("request_id")
        batch_op.drop_column("model")
        batch_op.drop_column("provider")
        batch_op.drop_column("provider_input")
