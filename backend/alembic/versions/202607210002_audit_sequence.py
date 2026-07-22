"""add deterministic audit sequence

Revision ID: 202607210002
Revises: 202607210001
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607210002"
down_revision: str | None = "202607210001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("sequence_number", sa.Integer(), nullable=True))
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        rows = connection.execute(sa.text("SELECT rowid, id FROM audit_logs ORDER BY rowid"))
    else:
        rows = connection.execute(
            sa.text("SELECT id FROM audit_logs ORDER BY created_at, id")
        )
    for sequence_number, row in enumerate(rows, start=1):
        connection.execute(
            sa.text("UPDATE audit_logs SET sequence_number = :sequence WHERE id = :id"),
            {"sequence": sequence_number, "id": row.id},
        )
    op.create_index(
        "ix_audit_logs_sequence_number",
        "audit_logs",
        ["sequence_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_logs_sequence_number", table_name="audit_logs")
    op.drop_column("audit_logs", "sequence_number")
