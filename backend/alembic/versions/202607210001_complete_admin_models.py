"""complete admin models

Revision ID: 202607210001
Revises: bd99ce5f9832
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa

revision = "202607210001"
down_revision = "bd99ce5f9832"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_templates",
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("format", sa.String(40), nullable=False),
        sa.Column("template_body", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_templates")),
    )
    op.create_index(op.f("ix_report_templates_name"), "report_templates", ["name"], unique=True)
    op.create_table(
        "platform_settings",
        sa.Column("scope", sa.String(80), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_platform_settings")),
        sa.UniqueConstraint("scope", "key", name="uq_platform_setting_scope_key"),
    )
    op.create_index(op.f("ix_platform_settings_scope"), "platform_settings", ["scope"])
    op.create_index(op.f("ix_platform_settings_key"), "platform_settings", ["key"])
    op.create_table(
        "notification_channels",
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("channel_type", sa.String(40), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notification_channels")),
    )
    op.create_index(op.f("ix_notification_channels_name"), "notification_channels", ["name"], unique=True)
    op.create_index(op.f("ix_notification_channels_channel_type"), "notification_channels", ["channel_type"])
    op.create_table(
        "ssh_gateway_profiles",
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ssh_gateway_profiles")),
    )
    op.create_index(op.f("ix_ssh_gateway_profiles_name"), "ssh_gateway_profiles", ["name"], unique=True)
    op.create_table(
        "ai_provider_configurations",
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("provider_type", sa.String(40), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("secret_reference", sa.String(160), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_provider_configurations")),
    )
    op.create_index(op.f("ix_ai_provider_configurations_name"), "ai_provider_configurations", ["name"], unique=True)
    op.create_index(op.f("ix_ai_provider_configurations_provider_type"), "ai_provider_configurations", ["provider_type"])
    op.create_index(op.f("ix_ai_provider_configurations_is_active"), "ai_provider_configurations", ["is_active"])


def downgrade() -> None:
    op.drop_table("ai_provider_configurations")
    op.drop_table("ssh_gateway_profiles")
    op.drop_table("notification_channels")
    op.drop_table("platform_settings")
    op.drop_table("report_templates")
