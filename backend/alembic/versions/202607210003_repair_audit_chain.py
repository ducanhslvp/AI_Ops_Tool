"""repair audit hashes using deterministic sequence

Revision ID: 202607210003
Revises: 202607210002
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from hashlib import sha256

from alembic import op
import sqlalchemy as sa

revision: str = "202607210003"
down_revision: str | None = "202607210002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

audit_logs = sa.table(
    "audit_logs",
    sa.column("id", sa.String()),
    sa.column("sequence_number", sa.Integer()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("user_id", sa.String()),
    sa.column("session_id", sa.String()),
    sa.column("server_id", sa.String()),
    sa.column("prompt", sa.Text()),
    sa.column("reasoning_summary", sa.Text()),
    sa.column("tool_name", sa.String()),
    sa.column("ssh_command", sa.Text()),
    sa.column("output", sa.Text()),
    sa.column("decision", sa.String()),
    sa.column("duration_ms", sa.Integer()),
    sa.column("result", sa.String()),
    sa.column("integrity_hash", sa.String()),
)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.select(audit_logs).order_by(audit_logs.c.sequence_number)
    ).mappings()
    previous_hash = "GENESIS"
    for row in rows:
        material = "|".join(
            [
                previous_hash,
                _as_utc(row["created_at"]).isoformat(),
                row["user_id"] or "",
                row["session_id"] or "",
                row["server_id"] or "",
                row["prompt"] or "",
                row["reasoning_summary"] or "",
                row["tool_name"] or "",
                row["ssh_command"] or "",
                row["output"] or "",
                row["decision"] or "",
                str(row["duration_ms"]),
                row["result"],
            ]
        )
        previous_hash = sha256(material.encode("utf-8")).hexdigest()
        connection.execute(
            audit_logs.update()
            .where(audit_logs.c.id == row["id"])
            .values(integrity_hash=previous_hash)
        )


def downgrade() -> None:
    # The previous defective ordering cannot be reconstructed deterministically.
    pass
