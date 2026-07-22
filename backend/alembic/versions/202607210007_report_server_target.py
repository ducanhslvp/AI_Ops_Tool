"""add optional report server target

Revision ID: 202607210007
Revises: 202607210006
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607210007"
down_revision: str | None = "202607210006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("reports") as batch:
        batch.add_column(sa.Column("server_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key("fk_reports_server_id", "servers", ["server_id"], ["id"])
        batch.create_index("ix_reports_server_id", ["server_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("reports") as batch:
        batch.drop_index("ix_reports_server_id")
        batch.drop_constraint("fk_reports_server_id", type_="foreignkey")
        batch.drop_column("server_id")
