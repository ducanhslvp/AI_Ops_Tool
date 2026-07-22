"""scope SSH credentials to systems

Revision ID: 202607220006
Revises: 202607220005
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607220006"
down_revision: str | None = "202607220005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("credentials") as batch:
        batch.add_column(sa.Column("system_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("username", sa.String(120), nullable=False,
                                   server_default=""))
        batch.create_foreign_key(
            "fk_credentials_system_id_systems", "systems", ["system_id"], ["id"]
        )
        batch.create_index("ix_credentials_system_id", ["system_id"], unique=False)
def downgrade() -> None:
    with op.batch_alter_table("credentials") as batch:
        batch.drop_index("ix_credentials_system_id")
        batch.drop_constraint("fk_credentials_system_id_systems", type_="foreignkey")
        batch.drop_column("username")
        batch.drop_column("system_id")
