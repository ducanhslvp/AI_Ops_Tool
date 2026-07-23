"""Ensure upgraded installations have a visible SSH Gateway runtime profile.

Revision ID: 202607230002
Revises: 202607230001
"""

from datetime import UTC, datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision = "202607230002"
down_revision = "202607230001"
branch_labels = None
depends_on = None

PROFILE_NAME = "default"
PROFILE_DESCRIPTION = "Default backend-controlled SSH Gateway limits"


def upgrade() -> None:
    connection = op.get_bind()
    profiles = sa.table(
        "ssh_gateway_profiles",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("config", sa.JSON),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    existing = connection.scalar(sa.select(sa.func.count()).select_from(profiles))
    if existing:
        return
    now = datetime.now(UTC)
    connection.execute(profiles.insert().values(
        id=str(uuid4()),
        name=PROFILE_NAME,
        description=PROFILE_DESCRIPTION,
        config={
            "connect_timeout_seconds": 10,
            "command_timeout_seconds": 30,
            "output_limit_bytes": 1_048_576,
            "max_attempts": 2,
            "known_hosts_file": "~/.ssh/known_hosts",
        },
        is_active=True,
        created_at=now,
        updated_at=now,
    ))


def downgrade() -> None:
    connection = op.get_bind()
    profiles = sa.table(
        "ssh_gateway_profiles",
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
    )
    connection.execute(profiles.delete().where(
        profiles.c.name == PROFILE_NAME,
        profiles.c.description == PROFILE_DESCRIPTION,
    ))
