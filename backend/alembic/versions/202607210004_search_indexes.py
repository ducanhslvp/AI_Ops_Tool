"""add enterprise search indexes

Revision ID: 202607210004
Revises: 202607210003
"""

from collections.abc import Sequence

from alembic import op

revision: str = "202607210004"
down_revision: str | None = "202607210003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_knowledge_documents_title", "knowledge_documents", ["title"])
    op.create_index("ix_reports_title", "reports", ["title"])
    op.create_index("ix_ai_sessions_title", "ai_sessions", ["title"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_alerts_created_at", table_name="alerts")
    op.drop_index("ix_ai_sessions_title", table_name="ai_sessions")
    op.drop_index("ix_reports_title", table_name="reports")
    op.drop_index("ix_knowledge_documents_title", table_name="knowledge_documents")
