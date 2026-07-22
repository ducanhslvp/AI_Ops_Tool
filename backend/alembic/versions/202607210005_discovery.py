"""add infrastructure discovery snapshots and schedules

Revision ID: 202607210005
Revises: 202607210004
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607210005"
down_revision: str | None = "202607210004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "discovery_scans",
        sa.Column("requested_by_user_id", sa.String(36), nullable=False),
        sa.Column("system_id", sa.String(36), nullable=True),
        sa.Column("baseline_scan_id", sa.String(36), nullable=True),
        sa.Column("scope_type", sa.String(40), nullable=False),
        sa.Column("server_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("nodes", sa.JSON(), nullable=False),
        sa.Column("edges", sa.JSON(), nullable=False),
        sa.Column("raw_evidence", sa.JSON(), nullable=False),
        sa.Column("change_summary", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["system_id"], ["systems.id"]),
        sa.ForeignKeyConstraint(["baseline_scan_id"], ["discovery_scans.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("requested_by_user_id", "system_id", "scope_type", "status"):
        op.create_index(f"ix_discovery_scans_{column}", "discovery_scans", [column])
    op.create_table(
        "discovery_schedules",
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("system_id", sa.String(36), nullable=True),
        sa.Column("server_ids", sa.JSON(), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("incremental", sa.Boolean(), nullable=False),
        sa.Column("include_system_services", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["system_id"], ["systems.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    for column in ("name", "system_id", "enabled", "next_run_at"):
        op.create_index(f"ix_discovery_schedules_{column}", "discovery_schedules", [column])


def downgrade() -> None:
    op.drop_table("discovery_schedules")
    op.drop_table("discovery_scans")
