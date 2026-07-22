"""add discovery schedule owner

Revision ID: 202607210006
Revises: 202607210005
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607210006"
down_revision: str | None = "202607210005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("discovery_schedules") as batch:
        batch.add_column(sa.Column("requested_by_user_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_discovery_schedules_requested_by_user_id_users",
                                 "users", ["requested_by_user_id"], ["id"])
        batch.create_index("ix_discovery_schedules_requested_by_user_id",
                           ["requested_by_user_id"])


def downgrade() -> None:
    with op.batch_alter_table("discovery_schedules") as batch:
        batch.drop_index("ix_discovery_schedules_requested_by_user_id")
        batch.drop_constraint("fk_discovery_schedules_requested_by_user_id_users",
                              type_="foreignkey")
        batch.drop_column("requested_by_user_id")
