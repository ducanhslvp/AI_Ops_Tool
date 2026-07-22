"""repair legacy AI session System scope from workspace metadata

Revision ID: 202607220003
Revises: 202607220002
"""

from collections.abc import Sequence
from pathlib import PurePath

from alembic import op
import sqlalchemy as sa

revision: str = "202607220003"
down_revision: str | None = "202607220002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    systems = sa.table("systems", sa.column("id", sa.String()), sa.column("code", sa.String()))
    sessions = sa.table(
        "ai_sessions", sa.column("id", sa.String()), sa.column("system_id", sa.String()),
        sa.column("memory", sa.JSON()),
    )
    by_code = {str(code).casefold(): system_id for system_id, code in connection.execute(
        sa.select(systems.c.id, systems.c.code)
    )}
    for session_id, memory in connection.execute(sa.select(sessions.c.id, sessions.c.memory)):
        if not isinstance(memory, dict):
            continue
        workspace_path = str(memory.get("workspace_path") or "").replace("\\", "/").rstrip("/")
        code = PurePath(workspace_path).name.casefold() if workspace_path else ""
        if code in by_code:
            connection.execute(
                sessions.update().where(sessions.c.id == session_id).values(system_id=by_code[code])
            )


def downgrade() -> None:
    # The previous assignment cannot be reconstructed without reintroducing incorrect scope.
    pass
