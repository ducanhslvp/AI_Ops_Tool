"""Add delegated AI session policy bypass permission.

Revision ID: 202607230004
Revises: 202607230003
"""

from alembic import op
import sqlalchemy as sa

revision = "202607230004"
down_revision = "202607230003"
branch_labels = None
depends_on = None

PERMISSION_ID = "permission-ai-policy-bypass"
PERMISSION_CODE = "ai:policy_bypass"


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "INSERT INTO permissions (id, code, description, created_at, updated_at) "
            "SELECT :id, :code, :description, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE code = :code)"
        ),
        {
            "id": PERMISSION_ID,
            "code": PERMISSION_CODE,
            "description": "Allows session-scoped AI Policy and Approval bypass",
        },
    )
    connection.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT roles.id, permissions.id FROM roles, permissions "
            "WHERE roles.name IN ('Admin', 'Operator') "
            "AND permissions.code = :code "
            "AND NOT EXISTS ("
            "SELECT 1 FROM role_permissions existing "
            "WHERE existing.role_id = roles.id "
            "AND existing.permission_id = permissions.id)"
        ),
        {"code": PERMISSION_CODE},
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_id IN "
            "(SELECT id FROM permissions WHERE code = :code)"
        ),
        {"code": PERMISSION_CODE},
    )
    connection.execute(
        sa.text("DELETE FROM permissions WHERE code = :code"),
        {"code": PERMISSION_CODE},
    )
