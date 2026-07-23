"""Add global SSH command scope and session-only policy bypass.

Revision ID: 202607230003
Revises: 202607230002
"""

from alembic import op
import sqlalchemy as sa

revision = "202607230003"
down_revision = "202607230002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("systems") as batch:
        batch.add_column(sa.Column("default_credential_id", sa.String(), nullable=True))
        batch.create_index("ix_systems_default_credential_id", ["default_credential_id"])
        batch.create_foreign_key(
            "fk_systems_default_credential_id_credentials",
            "credentials", ["default_credential_id"], ["id"],
        )
    with op.batch_alter_table("ai_command_approvals") as batch:
        batch.alter_column("system_id", existing_type=sa.String(), nullable=True)
        batch.alter_column("server_id", existing_type=sa.String(), nullable=True)
    with op.batch_alter_table("ai_sessions") as batch:
        batch.add_column(sa.Column("bypass_policy", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))


def downgrade() -> None:
    # Global rules cannot be represented by the old schema.
    op.execute("DELETE FROM ai_command_approvals WHERE system_id IS NULL OR server_id IS NULL")
    with op.batch_alter_table("ai_sessions") as batch:
        batch.drop_column("bypass_policy")
    with op.batch_alter_table("systems") as batch:
        batch.drop_constraint(
            "fk_systems_default_credential_id_credentials", type_="foreignkey"
        )
        batch.drop_index("ix_systems_default_credential_id")
        batch.drop_column("default_credential_id")
    with op.batch_alter_table("ai_command_approvals") as batch:
        batch.alter_column("server_id", existing_type=sa.String(), nullable=False)
        batch.alter_column("system_id", existing_type=sa.String(), nullable=False)
