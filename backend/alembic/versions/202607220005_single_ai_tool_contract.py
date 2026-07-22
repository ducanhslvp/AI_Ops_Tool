"""expose a single AI SSH tool and reset stale provider threads

Revision ID: 202607220005
Revises: 202607220004
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607220005"
down_revision: str | None = "202607220004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text(
        "DELETE FROM tool_configurations WHERE tool_name <> 'run_ssh_command'"
    ))
    op.execute(sa.text("UPDATE ai_sessions SET provider_session_id = NULL"))


def downgrade() -> None:
    # Removed overrides represented legacy built-in tools and cannot be reconstructed safely.
    pass
