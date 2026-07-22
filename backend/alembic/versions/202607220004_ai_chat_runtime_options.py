"""add per-conversation Codex runtime and context options

Revision ID: 202607220004
Revises: 202607220003
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607220004"
down_revision: str | None = "202607220003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_sessions") as batch:
        batch.add_column(sa.Column("model", sa.String(length=160), nullable=True))
        batch.add_column(sa.Column("reasoning_effort", sa.String(length=20), nullable=False,
                                   server_default="medium"))
        batch.add_column(sa.Column("include_full_memory", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
        batch.add_column(sa.Column("accept_all_commands", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
    with op.batch_alter_table("audit_logs") as batch:
        batch.add_column(sa.Column("exit_code", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("approval_used", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))
    op.create_table(
        "ai_command_approvals",
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("system_id", sa.String(length=36), sa.ForeignKey("systems.id"), nullable=False),
        sa.Column("server_id", sa.String(length=36), sa.ForeignKey("servers.id"), nullable=False),
        sa.Column("command_hash", sa.String(length=64), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "system_id", "server_id", "command_hash",
                            name="uq_ai_command_approval_scope"),
    )
    for column in ("user_id", "system_id", "server_id", "command_hash", "is_active"):
        op.create_index(f"ix_ai_command_approvals_{column}", "ai_command_approvals", [column])


def downgrade() -> None:
    op.drop_table("ai_command_approvals")
    with op.batch_alter_table("audit_logs") as batch:
        batch.drop_column("approval_used")
        batch.drop_column("exit_code")
    with op.batch_alter_table("ai_sessions") as batch:
        batch.drop_column("accept_all_commands")
        batch.drop_column("include_full_memory")
        batch.drop_column("reasoning_effort")
        batch.drop_column("model")
