"""split legacy global SSH credentials by system

Revision ID: 202607220007
Revises: 202607220006
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

from alembic import op
import sqlalchemy as sa

from app.services.secret_manager import LocalAesSecretManager

revision: str = "202607220007"
down_revision: str | None = "202607220006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()
    credentials = sa.Table("credentials", metadata, autoload_with=connection)
    servers = sa.Table("servers", metadata, autoload_with=connection)
    manager = LocalAesSecretManager()
    legacy = connection.execute(sa.select(credentials).where(
        credentials.c.system_id.is_(None)
    )).mappings().all()
    for credential in legacy:
        system_ids = list(connection.execute(
            sa.select(servers.c.system_id).where(
                servers.c.credential_id == credential["id"]
            ).distinct()
        ).scalars())
        if not system_ids:
            continue
        try:
            username = str(manager.decrypt(credential["encrypted_payload"]).get("username") or "")
        except Exception:
            username = ""
        source_id = credential["id"]
        now = datetime.now(UTC)
        for index, system_id in enumerate(system_ids):
            target_id = source_id if index == 0 else str(uuid4())
            if index == 0:
                connection.execute(credentials.update().where(
                    credentials.c.id == source_id
                ).values(system_id=system_id, username=username,
                         metadata_json={**(credential["metadata_json"] or {}),
                                        "scope": "shared"}))
            else:
                connection.execute(credentials.insert().values(
                    id=target_id,
                    name=f"{credential['name']}-{str(system_id)[:8]}",
                    system_id=system_id,
                    username=username,
                    provider=credential["provider"],
                    encrypted_payload=credential["encrypted_payload"],
                    metadata_json={**(credential["metadata_json"] or {}),
                                   "scope": "shared", "split_from": source_id},
                    is_active=credential["is_active"],
                    created_at=now,
                    updated_at=now,
                ))
            connection.execute(servers.update().where(
                servers.c.credential_id == source_id,
                servers.c.system_id == system_id,
            ).values(credential_id=target_id))


def downgrade() -> None:
    # System-scoped copies may have rotated independently and must never be merged automatically.
    pass
