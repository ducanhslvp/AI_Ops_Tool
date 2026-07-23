"""Add managed effects and usage metadata to remembered SSH commands."""

from alembic import op
import sqlalchemy as sa

revision = "202607230001"
down_revision = "202607220007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_command_approvals", sa.Column(
        "effect", sa.String(length=40), nullable=False, server_default="approval_required"
    ))
    op.add_column("ai_command_approvals", sa.Column(
        "description", sa.String(length=255), nullable=False, server_default=""
    ))
    op.add_column("ai_command_approvals", sa.Column(
        "use_count", sa.Integer(), nullable=False, server_default="0"
    ))
    op.add_column("ai_command_approvals", sa.Column(
        "last_used_at", sa.DateTime(timezone=True), nullable=True
    ))
    op.execute("UPDATE ai_command_approvals SET effect = 'allow' WHERE is_active = 1")
    op.create_index("ix_ai_command_approvals_effect", "ai_command_approvals", ["effect"])
    op.create_index(
        "ix_ai_command_approvals_last_used_at", "ai_command_approvals", ["last_used_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ai_command_approvals_last_used_at", table_name="ai_command_approvals")
    op.drop_index("ix_ai_command_approvals_effect", table_name="ai_command_approvals")
    op.drop_column("ai_command_approvals", "last_used_at")
    op.drop_column("ai_command_approvals", "use_count")
    op.drop_column("ai_command_approvals", "description")
    op.drop_column("ai_command_approvals", "effect")
