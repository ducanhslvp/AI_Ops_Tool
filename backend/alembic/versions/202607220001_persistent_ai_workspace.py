"""add persistent AI workspace session and memory metadata

Revision ID: 202607220001
Revises: 202607210009
"""

from collections.abc import Sequence
import json

from alembic import op
import sqlalchemy as sa

revision: str = "202607220001"
down_revision: str | None = "202607210009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("ai_sessions") as batch_op:
        batch_op.add_column(sa.Column("system_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("provider_session_id", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("status", sa.String(length=40), nullable=False,
                                      server_default="idle"))
        batch_op.add_column(sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("context_size", sa.Integer(), nullable=False,
                                      server_default="0"))
        batch_op.create_foreign_key("fk_ai_sessions_system_id_systems", "systems", ["system_id"], ["id"])
        batch_op.create_index("ix_ai_sessions_system_id", ["system_id"])
        batch_op.create_index("ix_ai_sessions_provider_session_id", ["provider_session_id"])
        batch_op.create_index("ix_ai_sessions_status", ["status"])
    op.create_table(
        "ai_memories",
        sa.Column("system_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("topic", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["system_id"], ["systems.id"], name="fk_ai_memories_system_id_systems"),
        sa.ForeignKeyConstraint(["session_id"], ["ai_sessions.id"], name="fk_ai_memories_session_id_ai_sessions"),
        sa.PrimaryKeyConstraint("id", name="pk_ai_memories"),
    )
    for column in ("system_id", "session_id", "category", "topic", "source_type",
                   "occurred_at", "archived_at"):
        op.create_index(f"ix_ai_memories_{column}", "ai_memories", [column])
    connection = op.get_bind()
    providers = sa.table(
        "ai_provider_configurations", sa.column("id", sa.String()),
        sa.column("provider_type", sa.String()), sa.column("config", sa.JSON()),
    )
    for provider_id, config in connection.execute(
        sa.select(providers.c.id, providers.c.config).where(providers.c.provider_type == "codex")
    ):
        value = dict(config or {}) if isinstance(config, dict) else json.loads(config or "{}")
        value["ephemeral"] = False
        connection.execute(
            providers.update().where(providers.c.id == provider_id).values(config=value)
        )
    connection.execute(sa.text(
        "UPDATE ai_sessions SET system_id = ("
        "SELECT servers.system_id FROM audit_logs JOIN servers ON servers.id = audit_logs.server_id "
        "WHERE audit_logs.session_id = ai_sessions.id LIMIT 1"
        ") WHERE system_id IS NULL"
    ))


def downgrade() -> None:
    op.drop_table("ai_memories")
    with op.batch_alter_table("ai_sessions") as batch_op:
        batch_op.drop_index("ix_ai_sessions_status")
        batch_op.drop_index("ix_ai_sessions_provider_session_id")
        batch_op.drop_index("ix_ai_sessions_system_id")
        batch_op.drop_constraint("fk_ai_sessions_system_id_systems", type_="foreignkey")
        batch_op.drop_column("context_size")
        batch_op.drop_column("last_activity_at")
        batch_op.drop_column("status")
        batch_op.drop_column("provider_session_id")
        batch_op.drop_column("system_id")
