"""persist Codex CLI runtime and health state

Revision ID: 202607210009
Revises: 202607210008
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

revision: str = "202607210009"
down_revision: str | None = "202607210008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_provider_configurations") as batch_op:
        batch_op.add_column(sa.Column("exclusive_mode", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
        batch_op.add_column(sa.Column("health_status", sa.String(length=40), nullable=False,
                                      server_default="unknown"))
        batch_op.add_column(sa.Column("health_detail", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("detected_version", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True))
    providers = sa.table(
        "ai_provider_configurations",
        sa.column("id", sa.String()), sa.column("name", sa.String()),
        sa.column("provider_type", sa.String()), sa.column("model", sa.String()),
        sa.column("config", sa.JSON()), sa.column("secret_reference", sa.String()),
        sa.column("enabled", sa.Boolean()), sa.column("is_active", sa.Boolean()),
        sa.column("exclusive_mode", sa.Boolean()), sa.column("health_status", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    connection = op.get_bind()
    connection.execute(providers.update().values(is_active=False, exclusive_mode=False))
    codex_id = connection.execute(
        sa.select(providers.c.id).where(providers.c.name == "codex-cli-local")
    ).scalar_one_or_none()
    if codex_id:
        connection.execute(
            providers.update().where(providers.c.id == codex_id).values(
                enabled=True, is_active=True, exclusive_mode=True
            )
        )
    else:
        now = datetime.now(timezone.utc)
        connection.execute(providers.insert().values(
            id=str(uuid4()), name="codex-cli-local", provider_type="codex", model="",
            config={"mode": "cli", "executable": "codex", "timeout_seconds": 120,
                    "ephemeral": True, "verify_authentication": True,
                    "max_output_bytes": 2_000_000},
            secret_reference=None, enabled=True, is_active=True, exclusive_mode=True,
            health_status="unknown", created_at=now, updated_at=now,
        ))


def downgrade() -> None:
    with op.batch_alter_table("ai_provider_configurations") as batch_op:
        batch_op.drop_column("last_health_check_at")
        batch_op.drop_column("detected_version")
        batch_op.drop_column("health_detail")
        batch_op.drop_column("health_status")
        batch_op.drop_column("exclusive_mode")
